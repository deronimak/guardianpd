"""Printing and reissuing pupil ID cards (School.credential_mode == "pupil").

School Admin only. Credentials are created lazily the first time a pupil's
card is printed, so switching a school to pupil mode needs no bulk
migration and enrolling a pupil needs no extra step.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_school, get_tenant_db, require_active_subscription, require_school_admin
from app.core.audit import record_audit, resolve_staff_actor_label
from app.core.qr_pdf import generate_pupil_cards_pdf
from app.core.security import generate_pupil_token
from app.models.platform import School
from app.models.tenant import Student, StudentCredential

router = APIRouter(prefix="/pupil-cards", tags=["pupil-cards"], dependencies=[Depends(require_school_admin)])


def _require_pupil_mode(school: School) -> None:
    if school.credential_mode != "pupil":
        raise HTTPException(status_code=403, detail="This school is not using pupil cards")


def _active_credential(tenant_db: Session, school: School, student: Student) -> StudentCredential:
    credential = (
        tenant_db.query(StudentCredential)
        .filter_by(student_id=student.id, revoked_at=None)
        .order_by(StudentCredential.issued_at.desc())
        .first()
    )
    if credential is None:
        credential = StudentCredential(student_id=student.id, token=generate_pupil_token(str(student.id), str(school.id)))
        tenant_db.add(credential)
        tenant_db.flush()
    return credential


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("")
def list_pupil_cards(
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
) -> list[dict]:
    """Every pupil with their card state, for the School Admin card screen."""
    _require_pupil_mode(school)
    credentials = {
        c.student_id: c for c in tenant_db.query(StudentCredential).filter(StudentCredential.revoked_at.is_(None)).all()
    }
    rows = []
    for student in tenant_db.query(Student).order_by(Student.name).all():
        cred = credentials.get(student.id)
        rows.append(
            {
                "student_id": student.id,
                "name": student.name,
                "grade": student.grade,
                "has_card": cred is not None,
                "print_count": cred.print_count if cred else 0,
                "last_printed_at": cred.last_printed_at if cred else None,
            }
        )
    return rows


@router.get("/bulk.pdf")
def download_bulk_cards(
    grade: str | None = None,
    school: School = Depends(require_active_subscription),
    tenant_db: Session = Depends(get_tenant_db),
) -> Response:
    """All pupils (or one class via ?grade=) in one PDF, front+back page per
    pupil, ready to feed through the card printer in one run."""
    _require_pupil_mode(school)
    query = tenant_db.query(Student).order_by(Student.grade, Student.name)
    if grade:
        query = query.filter(Student.grade == grade)
    students = query.all()
    if not students:
        raise HTTPException(status_code=404, detail="No pupils to print")

    now = datetime.now(timezone.utc)
    pupils = []
    for student in students:
        credential = _active_credential(tenant_db, school, student)
        credential.print_count += 1
        credential.last_printed_at = now
        pupils.append({"name": student.name, "grade": student.grade, "qr_token": credential.token})
    tenant_db.commit()

    pdf = generate_pupil_cards_pdf(pupils, school.name, school.logo)
    suffix = f"-{grade.replace(' ', '_')}" if grade else ""
    return _pdf_response(pdf, f"pupil-cards{suffix}.pdf")


@router.get("/{student_id}/card.pdf")
def download_pupil_card(
    student_id: uuid.UUID,
    school: School = Depends(require_active_subscription),
    tenant_db: Session = Depends(get_tenant_db),
) -> Response:
    _require_pupil_mode(school)
    student = tenant_db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Unknown pupil")

    credential = _active_credential(tenant_db, school, student)
    credential.print_count += 1
    credential.last_printed_at = datetime.now(timezone.utc)
    tenant_db.commit()

    pdf = generate_pupil_cards_pdf(
        [{"name": student.name, "grade": student.grade, "qr_token": credential.token}],
        school.name,
        school.logo,
    )
    return _pdf_response(pdf, f"{student.name.replace(' ', '_')}-pupil-card.pdf")


@router.post("/{student_id}/reissue")
def reissue_pupil_card(
    student_id: uuid.UUID,
    school: School = Depends(require_active_subscription),
    tenant_db: Session = Depends(get_tenant_db),
    claims: dict = Depends(get_current_staff),
) -> dict:
    """Lost or damaged card: the old QR stops working immediately and a
    fresh one is issued (print it with the card.pdf route)."""
    _require_pupil_mode(school)
    student = tenant_db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Unknown pupil")

    now = datetime.now(timezone.utc)
    for old in tenant_db.query(StudentCredential).filter_by(student_id=student_id, revoked_at=None).all():
        old.revoked_at = now
    tenant_db.add(StudentCredential(student_id=student_id, token=generate_pupil_token(str(student_id), str(school.id))))
    record_audit(
        tenant_db,
        "student",
        student_id,
        "updated",
        f"Reissued pupil card for {student.name}",
        resolve_staff_actor_label(tenant_db, claims),
    )
    tenant_db.commit()
    return {"student_id": student_id, "status": "reissued"}
