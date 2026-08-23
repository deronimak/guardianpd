import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_platform_staff
from app.core.security import create_access_token, hash_password, verify_password
from app.db.platform import get_platform_db
from app.models.platform import PlatformStaffUser
from app.schemas.auth import ChangePasswordRequest
from app.schemas.platform_auth import PlatformStaffLoginRequest, PlatformStaffTokenResponse

router = APIRouter(prefix="/auth/platform", tags=["platform-auth"])


@router.post("/login", response_model=PlatformStaffTokenResponse)
def platform_staff_login(
    payload: PlatformStaffLoginRequest,
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    """Real auth for the Master Admin console (ARCHITECTURE.md §10),
    replacing the old shared admin key. There's no signup here — accounts
    are created via `python -m app.jobs.create_platform_staff`.
    """
    staff = platform_db.query(PlatformStaffUser).filter_by(email=payload.email).first()
    if staff is None or not verify_password(payload.password, staff.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(subject=str(staff.id), extra_claims={"scope": "platform_ops", "role": staff.role})
    return {"access_token": token, "token_type": "bearer", "role": staff.role}


@router.post("/change-password")
def change_platform_password(
    payload: ChangePasswordRequest,
    claims: dict = Depends(require_platform_staff),
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    staff = platform_db.get(PlatformStaffUser, uuid.UUID(claims["sub"]))
    if staff is None or not verify_password(payload.current_password, staff.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    staff.password_hash = hash_password(payload.new_password)
    platform_db.commit()
    return {"status": "updated"}
