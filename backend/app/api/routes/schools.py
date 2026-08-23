"""Platform-level operations: enrolling a new school (ARCHITECTURE.md §4).

Not gated by X-School-Slug — this is where a school comes into existence,
so there's no tenant to resolve yet. Gated by a real PlatformStaffUser
login (require_platform_staff) — see app/jobs/create_platform_staff.py to
bootstrap an account.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_platform_staff
from app.core.email import send_email
from app.core.security import hash_password
from app.db.platform import SessionLocal, get_platform_db
from app.db.tenant import get_tenant_engine, get_tenant_sessionmaker, provision_tenant_database
from app.db.twophase import get_twophase_session
from app.models.platform import Invoice, School, Subscription
from app.models.tenant import StaffUser, Student, TenantBase
from app.schemas.school import SchoolDetailOut, SchoolEnrollRequest, SchoolOut, SchoolWithSubscriptionOut

router = APIRouter(prefix="/platform/schools", tags=["platform"], dependencies=[Depends(require_platform_staff)])

_BILLING_PERIOD_DAYS = 30


@router.get("", response_model=list[SchoolWithSubscriptionOut])
def list_schools(query: str | None = None, platform_db: Session = Depends(get_platform_db)) -> list[dict]:
    """Powers the Master Admin dashboard — search by either the auto-generated
    "GPD-XXXXXX" school ID (matched against the numeric sequence_no) or a
    substring of the school name.
    """
    q = platform_db.query(School)
    if query:
        stripped = query.strip().upper().removeprefix("GPD-").lstrip("0")
        if stripped.isdigit():
            q = q.filter(School.sequence_no == int(stripped))
        else:
            q = q.filter(School.name.ilike(f"%{query}%"))

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
                "created_at": school.created_at,
                "subscription_status": subscription.status if subscription else "none",
            }
        )
    return result


@router.get("/{school_id}", response_model=SchoolDetailOut)
def get_school_detail(school_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> dict:
    """Backs the dashboard's "link to each school": child count + the
    current billing-period window (ARCHITECTURE.md §4).
    """
    school = platform_db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Unknown school")

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
        "started_at": subscription.started_at if subscription else school.created_at,
        "current_period_start": current_period_start,
        "current_period_end": current_period_end,
        "child_count": child_count,
    }


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
