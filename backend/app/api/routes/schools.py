"""Platform-level operations: enrolling a new school (ARCHITECTURE.md §4).

Not gated by X-School-Slug — this is where a school comes into existence,
so there's no tenant to resolve yet. Gated by X-Platform-Admin-Key instead
(require_platform_admin) since this creates arbitrary schools/databases
and previously had no auth at all.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.core.security import hash_password
from app.db.platform import get_platform_db
from app.db.tenant import get_tenant_engine, get_tenant_sessionmaker, provision_tenant_database
from app.models.platform import School, Subscription
from app.models.tenant import StaffUser, TenantBase
from app.schemas.school import SchoolEnrollRequest, SchoolOut, SchoolWithSubscriptionOut

router = APIRouter(prefix="/platform/schools", tags=["platform"], dependencies=[Depends(require_platform_admin)])


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
                "created_at": school.created_at,
                "subscription_status": subscription.status if subscription else "none",
                "subscription_plan": subscription.plan if subscription else "none",
            }
        )
    return result


@router.post("", response_model=SchoolOut, status_code=201)
def enroll_school(payload: SchoolEnrollRequest, platform_db: Session = Depends(get_platform_db)) -> School:
    if platform_db.query(School).filter_by(slug=payload.slug).first() is not None:
        raise HTTPException(status_code=409, detail="A school with this slug already exists")

    school = School(
        name=payload.name,
        slug=payload.slug,
        tenant_db_name=f"tenant_{payload.slug.replace('-', '_')}",
        status="trial",
    )
    platform_db.add(school)
    platform_db.flush()  # need school.id before creating the Subscription row

    platform_db.add(Subscription(school_id=school.id, status="trialing"))

    # Provisioning + seeding the tenant DB happens outside the platform_db
    # transaction (it's a different physical database, so this can't be
    # made atomic with the platform_db commit below — see the note in
    # app/api/routes/guardians.py about the same limitation).
    provision_tenant_database(school.tenant_db_name)
    TenantBase.metadata.create_all(get_tenant_engine(school.tenant_db_name))

    tenant_session = get_tenant_sessionmaker(school.tenant_db_name)()
    try:
        tenant_session.add(
            StaffUser(
                name=payload.admin_name,
                email=payload.admin_email,
                password_hash=hash_password(payload.admin_temp_password),
                role="admin",
            )
        )
        tenant_session.commit()
    finally:
        tenant_session.close()

    platform_db.commit()
    return school
