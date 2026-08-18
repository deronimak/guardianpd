from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_school, get_tenant_db
from app.core.security import generate_qr_token
from app.db.platform import get_platform_db
from app.models.platform import GuardianMembership, PlatformUser, School
from app.models.tenant import Guardian, QRCredential
from app.schemas.guardian import GuardianCreateRequest, GuardianOut

router = APIRouter(prefix="/guardians", tags=["guardians"])


@router.post("", response_model=GuardianOut, status_code=201)
def create_guardian(
    payload: GuardianCreateRequest,
    school: School = Depends(get_school),
    platform_db: Session = Depends(get_platform_db),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    """School-initiated enrollment (ARCHITECTURE.md §8): staff creates the
    guardian record and prints their QR credential here; the parent's own
    account activation is a separate, later step and isn't required for
    this to work.

    Note: this writes to two separate physical databases (platform_db for
    the identity + membership rows, tenant_db for the guardian + QR
    credential) with two separate commits below — there's no cross-database
    transaction, so a crash between the two commits can leave them
    inconsistent. Acceptable for this scaffold; a production version should
    reconcile via a background job or outbox pattern.
    """
    platform_user = platform_db.query(PlatformUser).filter_by(email=payload.email).first()
    if platform_user is None:
        platform_user = PlatformUser(name=payload.name, email=payload.email, phone=payload.phone)
        platform_db.add(platform_user)
        platform_db.flush()

    guardian = Guardian(
        platform_user_id=platform_user.id,
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
    )
    tenant_db.add(guardian)
    tenant_db.flush()

    token = generate_qr_token(guardian_id=str(guardian.id), school_id=str(school.id))
    tenant_db.add(QRCredential(guardian_id=guardian.id, token=token))
    tenant_db.commit()

    platform_db.add(
        GuardianMembership(
            platform_user_id=platform_user.id,
            school_id=school.id,
            tenant_guardian_id=guardian.id,
        )
    )
    platform_db.commit()

    return {"id": guardian.id, "name": guardian.name, "qr_token": token}
