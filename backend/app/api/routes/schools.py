"""Platform-level operations: enrolling a new school (ARCHITECTURE.md §4).

Not gated by X-School-Slug — this is where a school comes into existence,
so there's no tenant to resolve yet. Gated by a real PlatformStaffUser
login (require_platform_staff) — see app/jobs/create_platform_staff.py to
bootstrap an account.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_platform_staff
from app.core.security import hash_password
from app.db.platform import SessionLocal, get_platform_db
from app.db.tenant import get_tenant_engine, provision_tenant_database
from app.db.twophase import get_twophase_session
from app.models.platform import School, Subscription
from app.models.tenant import StaffUser, TenantBase
from app.schemas.school import SchoolEnrollRequest, SchoolOut, SchoolWithSubscriptionOut

router = APIRouter(prefix="/platform/schools", tags=["platform"], dependencies=[Depends(require_platform_staff)])


@router.get("", response_model=list[SchoolWithSubscriptionOut])
def list_schools(platform_db: Session = Depends(get_platform_db)) -> list[dict]:
    """Powers the ops console (ARCHITECTURE.md §10) — there was previously
    no way to see enrolled schools at all short of querying the DB directly.
    """
    schools = platform_db.query(School).order_by(School.created_at.desc()).all()
    result = []
    for school in schools:
        subscription = platform_db.query(Subscription).filter_by(school_id=school.id).first()
        result.append(
            {
                "id": school.id,
                "name": school.name,
                "slug": school.slug,
                "status": school.status,
                "timezone": school.timezone,
                "billing_email": school.billing_email,
                "created_at": school.created_at,
                "subscription_status": subscription.status if subscription else "none",
                "subscription_plan": subscription.plan if subscription else "none",
            }
        )
    return result


@router.post("", response_model=SchoolOut, status_code=201)
def enroll_school(payload: SchoolEnrollRequest) -> School:
    """Creates the School/Subscription (platform DB) and first StaffUser
    (tenant DB) as a single atomic unit via two-phase commit (see
    app/db/twophase.py) — either all three exist or none do.

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
            status="trial",
            timezone=payload.timezone,
            billing_email=payload.billing_email or payload.admin_email,
        )
        db.add(school)
        db.flush()  # need school.id before the Subscription row

        db.add(Subscription(school_id=school.id, status="trialing"))
        db.add(
            StaffUser(
                name=payload.admin_name,
                email=payload.admin_email,
                password_hash=hash_password(payload.admin_temp_password),
                role="admin",
            )
        )
        db.commit()
        return school
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
