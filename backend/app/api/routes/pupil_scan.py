"""Pupil-card scanning (School.credential_mode == "pupil").

The pupil carries their own card, so a scan identifies the child directly:
no guardian is present, the arrival/departure direction is worked out from
the child's day so far, and every linked guardian is notified.

Scans can be captured OFFLINE on the gate device (flaky signal is the
normal case at many schools) and synced later in a batch. Each scan then
carries its real `scanned_at`; the server places it in that day's timeline,
so the arrival/departure direction, the attendance record and the message
parents receive all reflect when the child actually walked through the
gate, not when the phone reconnected.
"""

import datetime as dt
import zoneinfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_tenant_db, require_active_subscription
from app.api.routes.attendance import _guardians_for_student, _push_to_guardians
from app.core.security import verify_qr_token
from app.models.platform import School
from app.models.tenant import AttendanceEvent, Student, StudentCredential
from app.schemas.attendance import (
    PupilRosterEntry,
    PupilScanBatchRequest,
    PupilScanBatchResponse,
    PupilScanItem,
    PupilScanResult,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])

# Two scans of the same card inside this window are one physical tap
# (double-read, impatient second tap), not an arrival followed by a departure.
DUPLICATE_WINDOW = dt.timedelta(seconds=90)
# Tolerate small clock drift on the device; anything further ahead is clamped.
FUTURE_SKEW = dt.timedelta(minutes=5)
# Offline scans older than this are refused rather than silently rewriting
# history; a gate that has been offline for days needs a human to look.
MAX_OFFLINE_AGE = dt.timedelta(days=3)
# Parents are told the real time when a synced scan is this much older than now.
LATE_NOTICE_AFTER = dt.timedelta(minutes=3)


class _Rejected(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code


def _school_tz(school: School) -> zoneinfo.ZoneInfo | dt.timezone:
    try:
        return zoneinfo.ZoneInfo(school.timezone)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return dt.timezone.utc


def _require_pupil_mode(school: School) -> None:
    if school.credential_mode != "pupil":
        raise HTTPException(status_code=403, detail="This school is not using pupil cards")


def _next_type(tenant_db: Session, student_id, when: dt.datetime, tz) -> str:
    """drop_off / pick_up alternate through the school-local day, counting
    only events up to `when` (so a late-synced scan slots into place)."""
    local = when.astimezone(tz)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(dt.timezone.utc)
    previous = (
        tenant_db.query(AttendanceEvent)
        .filter(
            AttendanceEvent.student_id == student_id,
            AttendanceEvent.flagged.is_(False),
            AttendanceEvent.timestamp >= day_start,
            AttendanceEvent.timestamp < when,
        )
        .order_by(AttendanceEvent.timestamp.desc())
        .first()
    )
    if previous is None or previous.type == "pick_up":
        return "drop_off"
    return "pick_up"


def _record_pupil_scan(
    item: PupilScanItem,
    school: School,
    staff_id,
    tenant_db: Session,
) -> PupilScanResult:
    now = dt.datetime.now(dt.timezone.utc)
    when = item.scanned_at or now
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    if when > now + FUTURE_SKEW:
        raise _Rejected("Scan time is in the future; check the device clock")
    if when > now:
        when = now
    if now - when > MAX_OFFLINE_AGE:
        raise _Rejected("Scan is too old to sync; please record it manually with the school office")

    decoded = verify_qr_token(item.token)
    if decoded is None or decoded.get("sid") != str(school.id) or "pid" not in decoded:
        raise _Rejected("Invalid card")

    credential = tenant_db.query(StudentCredential).filter_by(token=item.token, revoked_at=None).first()
    if credential is None:
        raise _Rejected("This card is unrecognized or has been replaced")

    student = tenant_db.get(Student, credential.student_id)
    if student is None:
        raise _Rejected("This card is unrecognized or has been replaced")

    near = (
        tenant_db.query(AttendanceEvent)
        .filter(
            AttendanceEvent.student_id == student.id,
            AttendanceEvent.flagged.is_(False),
            AttendanceEvent.timestamp >= when - DUPLICATE_WINDOW,
            AttendanceEvent.timestamp <= when + DUPLICATE_WINDOW,
        )
        .first()
    )
    if near is not None:
        return PupilScanResult(
            status="duplicate",
            detail="Already scanned a moment ago",
            event_id=near.id,
            type=near.type,
            student_name=student.name,
            grade=student.grade,
            scanned_at=near.timestamp,
        )

    tz = _school_tz(school)
    event_type = _next_type(tenant_db, student.id, when, tz)
    event = AttendanceEvent(
        student_id=student.id,
        guardian_id=None,
        type=event_type,
        scanned_by_staff_id=staff_id,
        timestamp=when,
    )
    tenant_db.add(event)
    tenant_db.commit()

    action = "arrived at school" if event_type == "drop_off" else "left school"
    body = f"{student.name} {action}"
    if now - when > LATE_NOTICE_AFTER:
        body += f" at {when.astimezone(tz).strftime('%I:%M %p').lstrip('0')} (recorded earlier, delivered late)"
    else:
        body += f" ({school.name})"
    _push_to_guardians(
        tenant_db,
        _guardians_for_student(tenant_db, student.id),
        event.id,
        title=f"{student.name} {action}",
        body=body + ".",
    )

    return PupilScanResult(
        status="recorded",
        event_id=event.id,
        type=event_type,
        student_name=student.name,
        grade=student.grade,
        scanned_at=when,
    )


@router.post("/pupil-scan", response_model=PupilScanResult)
def pupil_scan(
    payload: PupilScanItem,
    school: School = Depends(require_active_subscription),
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> PupilScanResult:
    _require_pupil_mode(school)
    try:
        return _record_pupil_scan(payload, school, staff["sub"], tenant_db)
    except _Rejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/pupil-scan/batch", response_model=PupilScanBatchResponse)
def pupil_scan_batch(
    payload: PupilScanBatchRequest,
    school: School = Depends(require_active_subscription),
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> PupilScanBatchResponse:
    """Sync scans captured offline. Results come back in the same order as
    the request so the device can clear exactly what was accepted and keep
    (or surface) what was rejected. Scans are applied oldest-first so the
    arrival/departure alternation is right regardless of upload order.
    """
    _require_pupil_mode(school)
    now = dt.datetime.now(dt.timezone.utc)

    def sort_key(index: int) -> dt.datetime:
        when = payload.scans[index].scanned_at or now
        return when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)

    results: list[PupilScanResult | None] = [None] * len(payload.scans)
    for index in sorted(range(len(payload.scans)), key=sort_key):
        try:
            results[index] = _record_pupil_scan(payload.scans[index], school, staff["sub"], tenant_db)
        except _Rejected as exc:
            results[index] = PupilScanResult(status="rejected", detail=exc.detail)
    return PupilScanBatchResponse(results=results)  # type: ignore[arg-type]


@router.get("/pupil-roster", response_model=list[PupilRosterEntry])
def pupil_roster(
    school: School = Depends(require_active_subscription),
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> list[dict]:
    """Names for pupils holding an active card, cached on the gate device so
    it can show who just tapped even with no signal. Deliberately contains no
    tokens: the card's QR carries the pupil id, the device looks the name up
    here, and the server still validates the real signature at sync time.
    """
    _require_pupil_mode(school)
    rows = (
        tenant_db.query(Student)
        .join(StudentCredential, StudentCredential.student_id == Student.id)
        .filter(StudentCredential.revoked_at.is_(None))
        .order_by(Student.name)
        .all()
    )
    return [{"id": s.id, "name": s.name, "grade": s.grade} for s in rows]
