import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_tenant_db
from app.models.tenant import GuardianStudentLink, Student
from app.schemas.student import LinkCreateRequest, StudentCreateRequest, StudentOut

router = APIRouter(prefix="/students", tags=["students"], dependencies=[Depends(get_current_staff)])


@router.get("", response_model=list[StudentOut])
def list_students(tenant_db: Session = Depends(get_tenant_db)) -> list[Student]:
    """Powers the guardian-enrollment screen's "link to a student" picker —
    there was previously no way to see existing students short of querying
    the tenant DB directly.
    """
    return tenant_db.query(Student).order_by(Student.name).all()


@router.post("", response_model=StudentOut, status_code=201)
def create_student(payload: StudentCreateRequest, tenant_db: Session = Depends(get_tenant_db)) -> Student:
    student = Student(name=payload.name, dob=payload.dob, grade=payload.grade)
    tenant_db.add(student)
    tenant_db.commit()
    return student


@router.post("/{student_id}/guardians/{guardian_id}", status_code=201)
def link_guardian(
    student_id: uuid.UUID,
    guardian_id: uuid.UUID,
    payload: LinkCreateRequest,
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    """Many-to-many guardian<->student authorization link (ARCHITECTURE.md §3)."""
    link = GuardianStudentLink(
        student_id=student_id,
        guardian_id=guardian_id,
        relationship=payload.relationship,
        is_authorized_pickup=payload.is_authorized_pickup,
    )
    tenant_db.add(link)
    tenant_db.commit()
    return {"status": "linked", "link_id": link.id}
