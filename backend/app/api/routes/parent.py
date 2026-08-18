import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_parent
from app.db.platform import get_platform_db
from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import GuardianMembership, School
from app.models.tenant import GuardianDeviceToken, GuardianStudentLink, Student

router = APIRouter(prefix="/parent/me", tags=["parent"])


class DeviceRegisterRequest(BaseModel):
    token: str
    platform: Literal["ios", "android"]


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
