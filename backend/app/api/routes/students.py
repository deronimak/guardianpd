import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_tenant_db, require_school_admin
from app.core.audit import record_audit, resolve_staff_actor_label
from app.models.tenant import (
    AttendanceEvent,
    ExpectedAbsence,
    Guardian,
    GuardianStudentLink,
    Notification,
    Student,
    WelfareAlertLog,
)
from app.schemas.student import LinkCreateRequest, StudentCreateRequest, StudentOut, StudentUpdateRequest

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
def create_student(
    payload: StudentCreateRequest,
    tenant_db: Session = Depends(get_tenant_db),
    claims: dict = Depends(get_current_staff),
) -> Student:
    student = Student(name=payload.name, dob=payload.dob, grade=payload.grade)
    tenant_db.add(student)
    tenant_db.flush()
    record_audit(
        tenant_db, "student", student.id, "created", f"Added student {student.name}", resolve_staff_actor_label(tenant_db, claims)
    )
    tenant_db.commit()
    return student


@router.post("/{student_id}/guardians/{guardian_id}", status_code=201)
def link_guardian(
    student_id: uuid.UUID,
    guardian_id: uuid.UUID,
    payload: LinkCreateRequest,
    tenant_db: Session = Depends(get_tenant_db),
    claims: dict = Depends(get_current_staff),
) -> dict:
    """Many-to-many guardian<->student authorization link (ARCHITECTURE.md §3)."""
    link = GuardianStudentLink(
        student_id=student_id,
        guardian_id=guardian_id,
        relationship=payload.relationship,
        is_authorized_pickup=payload.is_authorized_pickup,
    )
    tenant_db.add(link)

    student = tenant_db.get(Student, student_id)
    guardian = tenant_db.get(Guardian, guardian_id)
    summary = f"Linked guardian {guardian.name if guardian else guardian_id} to student {student.name if student else student_id}"
    record_audit(tenant_db, "student", student_id, "linked", summary, resolve_staff_actor_label(tenant_db, claims))

    tenant_db.commit()
    return {"status": "linked", "link_id": link.id}


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: uuid.UUID,
    payload: StudentUpdateRequest,
    tenant_db: Session = Depends(get_tenant_db),
    claims: dict = Depends(get_current_staff),
) -> Student:
    """School-Admin-scoped edit — same shape as the Master Admin's
    equivalent (app/api/routes/schools.py) but reachable with just a staff
    JWT for this school, not a platform-staff login.
    """
    student = tenant_db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Unknown student")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(student, field, value)
    if updates:
        record_audit(
            tenant_db,
            "student",
            student.id,
            "updated",
            f"Updated student {student.name} ({', '.join(updates.keys())})",
            resolve_staff_actor_label(tenant_db, claims),
        )
    tenant_db.commit()
    tenant_db.refresh(student)
    return student


@router.delete("/{student_id}", status_code=204)
def delete_student(
    student_id: uuid.UUID,
    tenant_db: Session = Depends(get_tenant_db),
    claims: dict = Depends(get_current_staff),
) -> Response:
    """Hard delete — same cascade as the Master Admin's equivalent
    (app/api/routes/schools.py's delete_school_student): none of the FKs
    pointing at students.id cascade automatically, so dependent rows are
    cleaned up explicitly, in dependency order, inside one transaction.
    """
    student = tenant_db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Unknown student")
    student_name = student.name

    event_ids = [row.id for row in tenant_db.query(AttendanceEvent.id).filter_by(student_id=student_id).all()]
    if event_ids:
        tenant_db.query(Notification).filter(Notification.event_id.in_(event_ids)).delete(
            synchronize_session=False
        )
    tenant_db.query(AttendanceEvent).filter_by(student_id=student_id).delete(synchronize_session=False)
    tenant_db.query(ExpectedAbsence).filter_by(student_id=student_id).delete(synchronize_session=False)
    tenant_db.query(WelfareAlertLog).filter_by(student_id=student_id).delete(synchronize_session=False)
    tenant_db.query(GuardianStudentLink).filter_by(student_id=student_id).delete(synchronize_session=False)
    tenant_db.delete(student)
    record_audit(
        tenant_db, "student", student_id, "deleted", f"Deleted student {student_name}", resolve_staff_actor_label(tenant_db, claims)
    )
    tenant_db.commit()
    return Response(status_code=204)
