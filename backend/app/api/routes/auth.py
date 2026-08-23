import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_school, get_tenant_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.platform import School
from app.models.tenant import StaffUser
from app.schemas.auth import ChangePasswordRequest, StaffLoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/staff/login", response_model=TokenResponse)
def staff_login(
    payload: StaffLoginRequest,
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    staff = tenant_db.query(StaffUser).filter_by(email=payload.email).first()
    if staff is None or not verify_password(payload.password, staff.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        subject=str(staff.id),
        extra_claims={"school_id": str(school.id), "role": staff.role},
    )
    return {"access_token": token, "token_type": "bearer", "role": staff.role}


@router.post("/staff/change-password")
def change_staff_password(
    payload: ChangePasswordRequest,
    claims: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    """Covers both "change the school admin password" and a staff account's
    own password change — any authenticated staff member can change their
    own password, admin or not.
    """
    staff = tenant_db.get(StaffUser, uuid.UUID(claims["sub"]))
    if staff is None or not verify_password(payload.current_password, staff.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    staff.password_hash = hash_password(payload.new_password)
    tenant_db.commit()
    return {"status": "updated"}
