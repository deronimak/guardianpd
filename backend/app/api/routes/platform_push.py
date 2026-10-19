"""Master Admin push check — sends a real test notification to every phone a
parent has registered, and reports exactly what Firebase said per device. This
is how to tell whether push works on a particular phone (for example an
iPhone, where a missing Apple push key in Firebase fails every send) without
having to trigger a real school scan.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_platform_staff
from app.core.push import push_configured, send_push
from app.db.platform import get_platform_db
from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import GuardianMembership, PlatformUser, School
from app.models.tenant import GuardianDeviceToken

router = APIRouter(prefix="/platform/push", tags=["platform"], dependencies=[Depends(require_platform_staff)])


class PushTestRequest(BaseModel):
    email: str


@router.get("/status")
def push_status() -> dict:
    return {"configured": push_configured()}


@router.post("/test")
def send_test_push(payload: PushTestRequest, platform_db: Session = Depends(get_platform_db)) -> dict:
    user = platform_db.query(PlatformUser).filter(PlatformUser.email == payload.email.strip().lower()).first()
    if user is None:
        raise HTTPException(status_code=404, detail="No parent account with that email")

    devices: list[dict] = []
    seen: set[str] = set()
    for membership in platform_db.query(GuardianMembership).filter_by(platform_user_id=user.id).all():
        school = platform_db.get(School, membership.school_id)
        if school is None:
            continue
        tenant_db = get_tenant_sessionmaker(school.tenant_db_name)()
        try:
            rows = tenant_db.query(GuardianDeviceToken).filter_by(guardian_id=membership.tenant_guardian_id).all()
            for row in rows:
                if row.token in seen:  # same phone registered at several schools: send once
                    continue
                seen.add(row.token)
                try:
                    send_push(row.token, "GuardianPD test", "If you can read this, notifications are working on this phone.")
                    outcome = {"ok": True, "detail": "Sent" if push_configured() else "Not sent: Firebase is not configured (logged only)"}
                except Exception as exc:
                    outcome = {"ok": False, "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}
                devices.append(
                    {"school": school.slug, "registered_as": row.platform, "token_tail": row.token[-6:], **outcome}
                )
        finally:
            tenant_db.close()

    if not devices:
        raise HTTPException(
            status_code=404,
            detail="That parent has no phone registered for notifications. Open the parent app on the phone, sign in, and allow notifications.",
        )
    return {"email": user.email, "firebase_configured": push_configured(), "devices": devices}
