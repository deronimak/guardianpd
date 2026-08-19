"""Welfare/absence alert job — ARCHITECTURE.md §7.

For each subscribed, welfare-enabled school past its configured cutoff
time, finds students with no drop-off event today (or a drop-off but no
pick-up), and — unless an ExpectedAbsence covers today — emails every
guardian linked to that student and records a WelfareAlertLog row.

This module is meant to be invoked periodically by an external scheduler
(cron, Windows Task Scheduler, etc. — see README.md) rather than running
its own in-process scheduler. That's a deliberate choice: cutoff-time
gating plus WelfareAlertLog's uniqueness constraint make repeated calls
safe, so a simple "run me every 15 minutes" is enough — no need for
precise once-a-day triggering logic, and no extra scheduler dependency
running inside the API process (which would need its own care to avoid
double-running across multiple worker processes).
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
import zoneinfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.email import send_email
from app.db.platform import SessionLocal as PlatformSessionLocal
from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import School, Subscription
from app.models.tenant import (
    AttendanceEvent,
    ExpectedAbsence,
    Guardian,
    GuardianStudentLink,
    Notification,
    SchoolCalendar,
    Student,
    WelfareAlertLog,
)

logger = logging.getLogger(__name__)


def _is_school_day(tenant_db: Session, today: dt.date) -> bool:
    calendar_row = tenant_db.get(SchoolCalendar, today)
    if calendar_row is not None:
        return calendar_row.is_school_day
    return today.weekday() < 5  # Mon-Fri default when there's no explicit override


def _has_expected_absence(tenant_db: Session, student_id: uuid.UUID, today: dt.date) -> bool:
    return (
        tenant_db.query(ExpectedAbsence)
        .filter(
            ExpectedAbsence.student_id == student_id,
            ExpectedAbsence.start_date <= today,
            ExpectedAbsence.end_date >= today,
        )
        .first()
        is not None
    )


def _already_alerted(tenant_db: Session, student_id: uuid.UUID, today: dt.date, alert_type: str) -> bool:
    return (
        tenant_db.query(WelfareAlertLog)
        .filter_by(student_id=student_id, alert_date=today, alert_type=alert_type)
        .first()
        is not None
    )


def _guardians_for_student(tenant_db: Session, student_id: uuid.UUID) -> list[Guardian]:
    return (
        tenant_db.query(Guardian)
        .join(GuardianStudentLink, GuardianStudentLink.guardian_id == Guardian.id)
        .filter(GuardianStudentLink.student_id == student_id)
        .all()
    )


def _send_alert(
    tenant_db: Session,
    student: Student,
    alert_type: str,
    today: dt.date,
    subject: str,
    body: str,
) -> bool:
    """Returns True if an alert was actually sent (False if already logged today)."""
    if _already_alerted(tenant_db, student.id, today, alert_type):
        return False

    tenant_db.add(WelfareAlertLog(student_id=student.id, alert_date=today, alert_type=alert_type))

    guardians = _guardians_for_student(tenant_db, student.id)
    for guardian in guardians:
        if not guardian.email:
            continue
        send_email(to_email=guardian.email, subject=subject, body=body)
        tenant_db.add(Notification(guardian_id=guardian.id, event_id=None, channel="email"))

    tenant_db.commit()
    return True


def run_dropoff_check(school: School, tenant_db: Session, today: dt.date) -> int:
    """Returns the number of students newly alerted."""
    if not _is_school_day(tenant_db, today):
        return 0

    students_with_dropoff = {
        row[0]
        for row in tenant_db.query(AttendanceEvent.student_id)
        .filter(AttendanceEvent.type == "drop_off", func.date(AttendanceEvent.timestamp) == today)
        .all()
    }

    alerted = 0
    for student in tenant_db.query(Student).all():
        if student.id in students_with_dropoff:
            continue
        if _has_expected_absence(tenant_db, student.id, today):
            continue
        sent = _send_alert(
            tenant_db,
            student,
            "no_dropoff",
            today,
            subject=f"{student.name} hasn't been checked in today",
            body=(
                f"{student.name} has not been dropped off at {school.name} today. "
                "If this is expected (sick day, appointment, etc.), please mark it "
                "as a planned absence, or contact the school. If this is unexpected, "
                "please contact the school right away."
            ),
        )
        if sent:
            alerted += 1
    return alerted


def run_pickup_check(school: School, tenant_db: Session, today: dt.date) -> int:
    """Returns the number of students newly alerted."""
    if not _is_school_day(tenant_db, today):
        return 0

    dropped_off = {
        row[0]
        for row in tenant_db.query(AttendanceEvent.student_id)
        .filter(AttendanceEvent.type == "drop_off", func.date(AttendanceEvent.timestamp) == today)
        .all()
    }
    picked_up = {
        row[0]
        for row in tenant_db.query(AttendanceEvent.student_id)
        .filter(AttendanceEvent.type == "pick_up", func.date(AttendanceEvent.timestamp) == today)
        .all()
    }

    alerted = 0
    for student_id in dropped_off - picked_up:
        student = tenant_db.get(Student, student_id)
        if student is None or _has_expected_absence(tenant_db, student_id, today):
            continue
        sent = _send_alert(
            tenant_db,
            student,
            "no_pickup",
            today,
            subject=f"{student.name} has not been picked up yet",
            body=(
                f"{student.name} was dropped off at {school.name} today but has not "
                "been picked up yet. Please contact the school if you need help."
            ),
        )
        if sent:
            alerted += 1
    return alerted


def _school_local_now(school: School, utc_now: dt.datetime) -> dt.datetime:
    """Converts a UTC instant into this school's own local wall-clock time
    — cutoff times (School.drop_off_cutoff_time etc.) are local to each
    school, so two schools in different timezones must be evaluated
    independently rather than against one shared server-local clock.
    """
    try:
        tz = zoneinfo.ZoneInfo(school.timezone)
    except zoneinfo.ZoneInfoNotFoundError:
        logger.warning("%s: unknown timezone %r, treating as UTC", school.slug, school.timezone)
        tz = dt.timezone.utc
    return utc_now.astimezone(tz)


def run_welfare_checks_for_all_schools(now: dt.datetime | None = None) -> None:
    """`now`, if given, must be tz-aware (naive values are assumed UTC) —
    it's a single fixed instant in time, converted to each school's own
    local time below, not a wall-clock time itself.
    """
    utc_now = now or dt.datetime.now(dt.timezone.utc)
    if utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=dt.timezone.utc)

    platform_db = PlatformSessionLocal()
    try:
        schools = (
            platform_db.query(School)
            .join(Subscription, Subscription.school_id == School.id)
            .filter(
                Subscription.status.in_(("trialing", "active")),  # ARCHITECTURE.md §4: lapsed schools lose this job
                School.welfare_email_enabled.is_(True),
            )
            .all()
        )

        for school in schools:
            local_now = _school_local_now(school, utc_now)
            today = local_now.date()
            current_time = local_now.time()

            tenant_db = get_tenant_sessionmaker(school.tenant_db_name)()
            try:
                if current_time >= school.drop_off_cutoff_time:
                    dropoff_alerted = run_dropoff_check(school, tenant_db, today)
                    if dropoff_alerted:
                        logger.info("%s: sent %d no-dropoff alert(s)", school.slug, dropoff_alerted)
                if current_time >= school.pickup_cutoff_time:
                    pickup_alerted = run_pickup_check(school, tenant_db, today)
                    if pickup_alerted:
                        logger.info("%s: sent %d no-pickup alert(s)", school.slug, pickup_alerted)
            finally:
                tenant_db.close()
    finally:
        platform_db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_welfare_checks_for_all_schools()
