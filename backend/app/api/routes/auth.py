from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_school, get_tenant_db
from app.core.security import create_access_token, verify_password
from app.models.platform import School
from app.models.tenant import StaffUser
from app.schemas.auth import StaffLoginRequest, TokenResponse

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
    return {"access_token": token, "token_type": "bearer"}
