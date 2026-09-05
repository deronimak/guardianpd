"""Platform-level operations: enrolling a new school (ARCHITECTURE.md §4).

Not gated by X-School-Slug — this is where a school comes into existence,
so there's no tenant to resolve yet. Gated by a real PlatformStaffUser
login (require_platform_staff) — see app/jobs/create_platform_staff.py to
bootstrap an account.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_platform_staff
from app.core.audit import record_audit, resolve_platform_actor_label
from app.core.email import send_email
from app.core.security import hash_password
from app.db.platform import SessionLocal, get_platform_db
from app.db.tenant import get_tenant_engine, get_tenant_sessionmaker, provision_tenant_database
from app.db.twophase import get_twophase_session
from app.models.platform import Invoice, School, Subscription
from app.models.tenant import (
    AttendanceEvent,
    AuditLogEntry,
    ExpectedAbsence,
    Guardian,
    GuardianStudentLink,
    Notification,
    QRCredential,
    StaffUser,
    Student,
    TenantBase,
    WelfareAlertLog,
)
from app.schemas.audit import AuditLogEntryOut
from app.schemas.school import (
    SchoolDetailOut,
    SchoolEnrollRequest,
    SchoolOut,
    SchoolUpdateRequest,
    SchoolWithSubscriptionOut,
)
from app.schemas.student import StudentOut, StudentUpdateRequest

router = APIRouter(prefix="/platform/schools", tags=["platform"], dependencies=[Depends(require_platform_staff)])

_BILLING_PERIOD_DAYS = 30


def _get_school_or_404(school_id: uuid.UUID, platform_db: Session) -> School:
    school = platform_db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Unknown school")
    return school


@router.get("", response_model=list[SchoolWithSubscriptionOut])
def list_schools(
    query: str | None = None,
    include_archived: bool = False,
    platform_db: Session = Depends(get_platform_db),
) -> list[dict]:
    """Powers the Master Admin dashboard — search by the auto-generated
    "GPD-XXXXXX" school ID (matched against the numeric sequence_no), or a
    substring of the school name, phone number, or billing email. Archived
    schools are hidden unless `include_archived=true` (used by the
    console's "show archived" toggle, since an archived school can still
    be found and unarchived here).
    """
    q = platform_db.query(School)
    if not include_archived:
        q = q.filter(School.archived_at.is_(None))
    if query:
        stripped = query.strip().upper().removeprefix("GPD-").lstrip("0")
        # A bare numeric query only means "sequence number" when it's short
        # enough to plausibly be one (the format is 6 digits, zero-padded) —
        # otherwise a phone number typed without its "+"/formatting (e.g.
        # "2348099999999") would incorrectly match here instead of falling
        # through to the phone/email/name search below.
        if stripped.isdigit() and len(stripped) <= 6:
            q = q.filter(School.sequence_no == int(stripped))
        else:
            like = f"%{query}%"
            q = q.filter(
                School.name.ilike(like) | School.phone.ilike(like) | School.billing_email.ilike(like)
            )

    schools = q.order_by(School.created_at.desc()).all()
    result = []
    for school in schools:
        subscription = platform_db.query(Subscription).filter_by(school_id=school.id).first()
        result.append(
            {
                "id": school.id,
                "sequence_no": school.sequence_no,
                "name": school.name,
                "slug": school.slug,
                "status": school.status,
                "timezone": school.timezone,
                "billing_email": school.billing_email,
                "phone": school.phone,
                "created_at": school.created_at,
                "subscription_status": subscription.status if subscription else "none",
                "archived_at": school.archived_at,
            }
        )
    return result


@router.get("/{school_id}", response_model=SchoolDetailOut)
def get_school_detail(school_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> dict:
    """Backs the dashboard's "link to each school": child count + the
    current billing-period window (ARCHITECTURE.md §4).
    """
    school = _get_school_or_404(school_id, platform_db)

    subscription = platform_db.query(Subscription).filter_by(school_id=school.id).first()
    latest_invoice = (
        platform_db.query(Invoice)
        .filter_by(school_id=school.id)
        .order_by(Invoice.period_end.desc())
        .first()
    )
    if latest_invoice is not None:
        current_period_start = latest_invoice.period_start
        current_period_end = latest_invoice.period_end
    else:
        anchor = subscription.started_at.date() if subscription else school.created_at.date()
        current_period_start = anchor
        current_period_end = anchor + dt.timedelta(days=_BILLING_PERIOD_DAYS)

    tenant_db = get_tenant_sessionmaker(school.tenant_db_name)()
    try:
        child_count = tenant_db.query(Student).count()
        guardian_count = tenant_db.query(Guardian).count()
        qr_printed_count = tenant_db.query(func.coalesce(func.sum(QRCredential.print_count), 0)).scalar() or 0
    finally:
        tenant_db.close()

    return {
        "id": school.id,
        "sequence_no": school.sequence_no,
        "name": school.name,
        "slug": school.slug,
        "address": school.address,
        "phone": school.phone,
        "timezone": school.timezone,
        "billing_email": school.billing_email,
        "subscription_status": subscription.status if subscription else "none",
        "price_per_child_naira": subscription.price_per_child_naira if subscription else 500,
        "started_at": subscription.started_at if subscription else school.created_at,
        "current_period_start": current_period_start,
        "current_period_end": current_period_end,
        "child_count": child_count,
        "guardian_count": guardian_count,
        "qr_printed_count": qr_printed_count,
        "archived_at": school.archived_at,
    }


@router.patch("/{school_id}", response_model=SchoolOut)
def update_school(
    school_id: uuid.UUID,
    payload: SchoolUpdateRequest,
    platform_db: Session = Depends(get_platform_db),
) -> School:
    """Edit a school's own record. `slug` isn't in SchoolUpdateRequest at
    all — it's baked into the tenant database name at enrollment and isn't
    safe to change after the fact.
    """
    school = _get_school_or_404(school_id, platform_db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(school, field, value)
    platform_db.commit()
    platform_db.refresh(school)
    return school


@router.post("/{school_id}/archive", response_model=SchoolOut)
def archive_school_record(school_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> School:
    """Removes the school from the default dashboard list and blocks staff
    login/scanning (app/api/deps.py's get_school) — deliberately NOT a hard
    delete. The tenant database and every guardian/child/attendance record
    in it are untouched and fully recoverable via .../unarchive.
    """
    school = _get_school_or_404(school_id, platform_db)
    if school.archived_at is None:
        school.archived_at = dt.datetime.now(dt.timezone.utc)
        platform_db.commit()
        platform_db.refresh(school)
    return school


@router.post("/{school_id}/unarchive", response_model=SchoolOut)
def unarchive_school_record(school_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> School:
    school = _get_school_or_404(school_id, platform_db)
    school.archived_at = None
    platform_db.commit()
    platform_db.refresh(school)
    return school


def _tenant_session_for(school: School):
    return get_tenant_sessionmaker(school.tenant_db_name)()


@router.get("/{school_id}/students", response_model=list[StudentOut])
def search_school_students(
    school_id: uuid.UUID,
    query: str | None = None,
    platform_db: Session = Depends(get_platform_db),
) -> list[Student]:
    """Master Admin child search (independent of the school-admin-scoped
    /students routes in app/api/routes/students.py, which require a staff
    JWT for that specific school) — this one is reachable directly from the
    platform-staff-authenticated console for any school by id.
    """
    school = _get_school_or_404(school_id, platform_db)
    tenant_db = _tenant_session_for(school)
    try:
        q = tenant_db.query(Student)
        if query:
            q = q.filter(Student.name.ilike(f"%{query}%"))
        return q.order_by(Student.name).all()
    finally:
        tenant_db.close()


@router.patch("/{school_id}/students/{student_id}", response_model=StudentOut)
def update_school_student(
    school_id: uuid.UUID,
    student_id: uuid.UUID,
    payload: StudentUpdateRequest,
    claims: dict = Depends(require_platform_staff),
    platform_db: Session = Depends(get_platform_db),
) -> Student:
    school = _get_school_or_404(school_id, platform_db)
    tenant_db = _tenant_session_for(school)
    try:
        student = tenant_db.get(Student, student_id)
        if student is None:
            raise HTTPException(status_code=404, detail="Unknown student at this school")
        updated_fields = list(payload.model_dump(exclude_unset=True).keys())
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(student, field, value)
        record_audit(
            tenant_db,
            "student",
            student.id,
            "updated",
            f"Updated student {student.name} ({', '.join(updated_fields)})",
            resolve_platform_actor_label(platform_db, claims),
        )
        tenant_db.commit()
        tenant_db.refresh(student)
        return student
    finally:
        tenant_db.close()


@router.delete("/{school_id}/students/{student_id}", status_code=204)
def delete_school_student(
    school_id: uuid.UUID,
    student_id: uuid.UUID,
    claims: dict = Depends(require_platform_staff),
    platform_db: Session = Depends(get_platform_db),
) -> Response:
    """Hard delete — a single child is low enough blast radius to just
    remove outright (unlike archiving a whole school). None of the FKs
    pointing at students.id are ON DELETE CASCADE, so dependent rows are
    cleaned up explicitly, in dependency order, inside one transaction:
    Notification (via AttendanceEvent) -> AttendanceEvent -> ExpectedAbsence
    -> WelfareAlertLog -> GuardianStudentLink -> Student.
    """
    school = _get_school_or_404(school_id, platform_db)
    tenant_db = _tenant_session_for(school)
    try:
        student = tenant_db.get(Student, student_id)
        if student is None:
            raise HTTPException(status_code=404, detail="Unknown student at this school")
        student_name = student.name

        event_ids = [
            row.id for row in tenant_db.query(AttendanceEvent.id).filter_by(student_id=student_id).all()
        ]
        if event_ids:
            tenant_db.query(Notification).filter(Notification.event_id.in_(event_ids)).delete(
                synchronize_session=False
            )
        tenant_db.query(AttendanceEvent).filter_by(student_id=student_id).delete(synchronize_session=False)
        tenant_db.query(ExpectedAbsence).filter_by(student_id=student_id).delete(synchronize_session=False)
        tenant_db.query(WelfareAlertLog).filter_by(student_id=student_id).delete(synchronize_session=False)
        tenant_db.query(GuardianStudentLink).filter_by(student_id=student_id).delete(synchronize_session=False)
        tenant_db.delete(student)
        record_audit(
            tenant_db,
            "student",
            student_id,
            "deleted",
            f"Deleted student {student_name}",
            resolve_platform_actor_label(platform_db, claims),
        )
        tenant_db.commit()
    finally:
        tenant_db.close()
    return Response(status_code=204)


@router.get("/{school_id}/audit-log", response_model=list[AuditLogEntryOut])
def get_school_audit_log(
    school_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    platform_db: Session = Depends(get_platform_db),
) -> list[AuditLogEntry]:
    """Master Admin's per-school Activity log — guardian/student
    add/edit/delete/link events (app/core/audit.py), newest first.
    """
    school = _get_school_or_404(school_id, platform_db)
    tenant_db = _tenant_session_for(school)
    try:
        return (
            tenant_db.query(AuditLogEntry)
            .order_by(AuditLogEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
    finally:
        tenant_db.close()


@router.post("", response_model=SchoolOut, status_code=201)
def enroll_school(payload: SchoolEnrollRequest) -> School:
    """Creates the School/Subscription (platform DB) and first StaffUser
    (tenant DB, role="admin" — this *is* the School Admin account) as a
    single atomic unit via two-phase commit (see app/db/twophase.py) —
    either all three exist or none do.

    Tenant DB provisioning + table creation happens first, outside that
    transaction, since PostgreSQL can't run CREATE DATABASE inside any
    transaction at all (2PC or not). That's fine: it's idempotent-safe to
    retry (provision_tenant_database checks pg_database before creating),
    so if the atomic write below fails, re-enrolling the same slug just
    re-provisions the same now-empty tenant DB rather than leaving anything
    inconsistent — the slug-uniqueness check below only ever passes once a
    School row actually committed.
    """
    precheck = SessionLocal()
    try:
        if precheck.query(School).filter_by(slug=payload.slug).first() is not None:
            raise HTTPException(status_code=409, detail="A school with this slug already exists")
    finally:
        precheck.close()

    tenant_db_name = f"tenant_{payload.slug.replace('-', '_')}"
    provision_tenant_database(tenant_db_name)
    TenantBase.metadata.create_all(get_tenant_engine(tenant_db_name))

    db = get_twophase_session(tenant_db_name)
    try:
        school = School(
            name=payload.name,
            slug=payload.slug,
            tenant_db_name=tenant_db_name,
            status="active",
            address=payload.address,
            phone=payload.phone,
            timezone=payload.timezone,
            billing_email=payload.billing_email or payload.admin_email,
        )
        db.add(school)
        db.flush()  # need school.id/sequence_no before the Subscription row

        db.add(Subscription(school_id=school.id, status="active"))
        db.add(
            StaffUser(
                name=payload.admin_name,
                email=payload.admin_email,
                password_hash=hash_password(payload.admin_temp_password),
                role="admin",
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    send_email(
        to_email=payload.admin_email,
        subject="Welcome to GuardianPD",
        body=(
            f"{payload.name} has been enrolled in GuardianPD.\n\n"
            f"School ID: GPD-{school.sequence_no:06d}\n"
            f"Log in via the mobile app's School Admin button using this email address.\n\n"
            "From there you can add staff accounts and enroll guardians."
        ),
    )

    return school
