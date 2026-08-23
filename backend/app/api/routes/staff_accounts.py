"""School-admin-managed staff accounts (GuardianPD spec).

Distinct from app/api/routes/auth.py (login/change-password) — this is
account *creation*, gated to School Admins only. There was previously no
way to create a StaffUser after the one "admin" account made at school
enrollment (app/api/routes/schools.py) — School Staff accounts didn't
exist as a concept at all.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_db, require_school_admin
from app.core.security import hash_password
from app.models.tenant import StaffUser
from app.schemas.staff import StaffAccountCreateRequest, StaffAccountOut

router = APIRouter(prefix="/staff", tags=["staff"], dependencies=[Depends(require_school_admin)])


@router.post("", response_model=StaffAccountOut, status_code=201)
def create_staff_account(
    payload: StaffAccountCreateRequest,
    tenant_db: Session = Depends(get_tenant_db),
) -> StaffUser:
    if tenant_db.query(StaffUser).filter_by(email=payload.username).first() is not None:
        raise HTTPException(status_code=409, detail="That username is already taken")

    staff = StaffUser(
        name=payload.username,
        email=payload.username,
        password_hash=hash_password(payload.password),
        role="staff",
    )
    tenant_db.add(staff)
    tenant_db.commit()
    return staff
