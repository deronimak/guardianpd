import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_tenant_db
from app.models.tenant import ExpectedAbsence
from app.schemas.absence import ExpectedAbsenceCreateRequest, ExpectedAbsenceOut

router = APIRouter(prefix="/students", tags=["absences"])


@router.post("/{student_id}/expected-absences", response_model=ExpectedAbsenceOut, status_code=201)
def create_expected_absence(
    student_id: uuid.UUID,
    payload: ExpectedAbsenceCreateRequest,
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> ExpectedAbsence:
    """Required input for the welfare job (ARCHITECTURE.md §7) — without a
    planned-absence record, every legitimate absence would trigger a false
    alarm. Staff-created for now, since parent login/auth isn't built yet
    (see README "not yet built"); a self-service parent version should call
    this same endpoint once that exists.
    """
    absence = ExpectedAbsence(
        student_id=student_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        created_by=staff["sub"],
    )
    tenant_db.add(absence)
    tenant_db.commit()
    return absence
