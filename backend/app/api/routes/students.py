import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_db, require_school_admin
from app.models.tenant import GuardianStudentLink, Student
from app.schemas.student import LinkCreateRequest, StudentCreateRequest, StudentOut

router = APIRouter(prefix="/students", tags=["students"], dependencies=[Depends(require_school_admin)])


@router.get("", response_model=list[StudentOut])
def list_students(tenant_db: Session = Depends(get_tenant_db)) -> list[Student]:
    """Powers the School Admin's "link an existing guardian to another
    student" screen — the primary enrollment path is now the combined
    guardian+children form (POST /guardians), but this stays available for
    adding a later sibling to an already-enrolled guardian.
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
