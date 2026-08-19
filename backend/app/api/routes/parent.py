import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_parent
from app.db.platform import get_platform_db
from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import GuardianMembership, School
from app.models.tenant import (
    AttendanceEvent,
    ExpectedAbsence,
    Guardian,
    GuardianDeviceToken,
    GuardianStudentLink,
    Student,
)
from app.schemas.absence import ExpectedAbsenceCreateRequest

router = APIRouter(prefix="/parent/me", tags=["parent"])


class DeviceRegisterRequest(BaseModel):
    token: str
    platform: Literal["ios", "android"]


def _authorize_parent_for_student(
    platform_db: Session,
    school_slug: str,
    student_id: uuid.UUID,
    platform_user_id: uuid.UUID,
) -> tuple[School, Session]:
    """Verifies this parent actually has a GuardianStudentLink to this
    student before letting them read/write anything about them — the same
    trust boundary as ARCHITECTURE.md §5/§6, just from the parent side.
    Caller owns the returned tenant Session and must close() it.
    """
    school = platform_db.query(School).filter_by(slug=school_slug).first()
    if school is None:
        raise HTTPException(status_code=404, detail="Unknown school")

    membership = (
        platform_db.query(GuardianMembership)
        .filter_by(platform_user_id=platform_user_id, school_id=school.id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Not linked to this school")

    tenant_db = get_tenant_sessionmaker(school.tenant_db_name)()
    link = (
        tenant_db.query(GuardianStudentLink)
        .filter_by(guardian_id=membership.tenant_guardian_id, student_id=student_id)
        .first()
    )
    if link is None:
        tenant_db.close()
        raise HTTPException(status_code=403, detail="You are not linked to this student")

    return school, tenant_db


@router.get("/children")
def my_children(
    parent: dict = Depends(get_current_parent),
    platform_db: Session = Depends(get_platform_db),
) -> list[dict]:
    """Aggregates linked children across every enrolled school this parent
    touches (ARCHITECTURE.md §2/§8) — one login, N tenant DBs queried.
    """
    platform_user_id = uuid.UUID(parent["sub"])
    memberships = platform_db.query(GuardianMembership).filter_by(platform_user_id=platform_user_id).all()

    children: list[dict] = []
    for membership in memberships:
        school = platform_db.get(School, membership.school_id)
        if school is None:
            continue
        tenant_db = get_tenant_sessionmaker(school.tenant_db_name)()
        try:
            links = tenant_db.query(GuardianStudentLink).filter_by(guardian_id=membership.tenant_guardian_id).all()
            for link in links:
                student = tenant_db.get(Student, link.student_id)
                if student is None:
                    continue
                children.append(
                    {
                        "school_slug": school.slug,
                        "school_name": school.name,
                        "student_id": str(student.id),
                        "student_name": student.name,
                        "grade": student.grade,
                        "is_authorized_pickup": link.is_authorized_pickup,
                    }
                )
        finally:
            tenant_db.close()

    return children


@router.post("/devices", status_code=201)
def register_device(
    payload: DeviceRegisterRequest,
    parent: dict = Depends(get_current_parent),
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    """Registers one physical-device push token against every school this
    parent is linked to — push fan-out on scan (app/api/routes/attendance.py)
    looks up tokens per tenant-local Guardian row, so the same token needs a
    row in each relevant tenant DB.
    """
    platform_user_id = uuid.UUID(parent["sub"])
    memberships = platform_db.query(GuardianMembership).filter_by(platform_user_id=platform_user_id).all()

    for membership in memberships:
        school = platform_db.get(School, membership.school_id)
        if school is None:
            continue
        tenant_db = get_tenant_sessionmaker(school.tenant_db_name)()
        try:
            existing = tenant_db.query(GuardianDeviceToken).filter_by(token=payload.token).first()
            if existing is None:
                tenant_db.add(
                    GuardianDeviceToken(
                        guardian_id=membership.tenant_guardian_id,
                        token=payload.token,
                        platform=payload.platform,
                    )
                )
                tenant_db.commit()
        finally:
            tenant_db.close()

    return {"status": "registered"}


@router.get("/schools/{school_slug}/students/{student_id}/attendance")
def student_attendance_history(
    school_slug: str,
    student_id: uuid.UUID,
    parent: dict = Depends(get_current_parent),
    platform_db: Session = Depends(get_platform_db),
) -> list[dict]:
    school, tenant_db = _authorize_parent_for_student(
        platform_db, school_slug, student_id, uuid.UUID(parent["sub"])
    )
    try:
        events = (
            tenant_db.query(AttendanceEvent)
            .filter_by(student_id=student_id)
            .order_by(AttendanceEvent.timestamp.desc())
            .limit(100)
            .all()
        )
        guardian_ids = {e.guardian_id for e in events}
        guardians = (
            {g.id: g for g in tenant_db.query(Guardian).filter(Guardian.id.in_(guardian_ids)).all()}
            if guardian_ids
            else {}
        )
        return [
            {
                "id": str(event.id),
                "type": event.type,
                "timestamp": event.timestamp.isoformat(),
                "guardian_name": guardians[event.guardian_id].name if event.guardian_id in guardians else None,
                "flagged": event.flagged,
            }
            for event in events
        ]
    finally:
        tenant_db.close()


@router.get("/schools/{school_slug}/students/{student_id}/expected-absences")
def list_expected_absences(
    school_slug: str,
    student_id: uuid.UUID,
    parent: dict = Depends(get_current_parent),
    platform_db: Session = Depends(get_platform_db),
) -> list[dict]:
    school, tenant_db = _authorize_parent_for_student(
        platform_db, school_slug, student_id, uuid.UUID(parent["sub"])
    )
    try:
        absences = (
            tenant_db.query(ExpectedAbsence)
            .filter_by(student_id=student_id)
            .order_by(ExpectedAbsence.start_date.desc())
            .all()
        )
        return [
            {
                "id": str(a.id),
                "start_date": a.start_date.isoformat(),
                "end_date": a.end_date.isoformat(),
                "reason": a.reason,
            }
            for a in absences
        ]
    finally:
        tenant_db.close()


@router.post("/schools/{school_slug}/students/{student_id}/expected-absences", status_code=201)
def create_expected_absence_as_parent(
    school_slug: str,
    student_id: uuid.UUID,
    payload: ExpectedAbsenceCreateRequest,
    parent: dict = Depends(get_current_parent),
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    """The self-service counterpart to the staff-only endpoint in
    app/api/routes/absences.py — ARCHITECTURE.md §7/§8. Same authorization
    boundary as the attendance history above: a parent can only mark
    absences for a student they're actually linked to.
    """
    school, tenant_db = _authorize_parent_for_student(
        platform_db, school_slug, student_id, uuid.UUID(parent["sub"])
    )
    try:
        absence = ExpectedAbsence(
            student_id=student_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            reason=payload.reason,
            created_by=f"parent:{parent['sub']}",
        )
        tenant_db.add(absence)
        tenant_db.commit()
        return {"id": str(absence.id), "status": "created"}
    finally:
        tenant_db.close()
