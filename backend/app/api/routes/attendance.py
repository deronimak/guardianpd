from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_tenant_db, require_active_subscription
from app.core.push import send_push
from app.core.security import verify_qr_token
from app.models.platform import School
from app.models.tenant import (
    AttendanceEvent,
    Guardian,
    GuardianDeviceToken,
    GuardianStudentLink,
    Notification,
    QRCredential,
    Student,
)
from app.schemas.attendance import ScanRequest, ScanResponse

router = APIRouter(prefix="/attendance", tags=["attendance"])

_ACTION_LABEL = {"drop_off": "dropped off", "pick_up": "picked up"}


def _guardians_for_student(tenant_db: Session, student_id) -> list[Guardian]:
    return (
        tenant_db.query(Guardian)
        .join(GuardianStudentLink, GuardianStudentLink.guardian_id == Guardian.id)
        .filter(GuardianStudentLink.student_id == student_id)
        .all()
    )


def _push_to_guardians(tenant_db: Session, guardians: list[Guardian], event_id, title: str, body: str) -> None:
    for guardian in guardians:
        devices = tenant_db.query(GuardianDeviceToken).filter_by(guardian_id=guardian.id).all()
        for device in devices:
            send_push(device.token, title=title, body=body)
        # One Notification row per guardian even with zero devices registered
        # yet — keeps an auditable record that we tried, per ARCHITECTURE.md §7.
        tenant_db.add(Notification(guardian_id=guardian.id, event_id=event_id, channel="push"))
    tenant_db.commit()


@router.post("/scan", response_model=ScanResponse)
def scan_qr(
    payload: ScanRequest,
    school: School = Depends(require_active_subscription),
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    """The core security-critical flow — ARCHITECTURE.md §5/§6.

    Order matters: subscription gate (dependency) -> signature check ->
    revocation check (DB) -> per-child authorization check (DB) -> write.
    scanned_by_staff_id comes from the authenticated staff JWT, never from
    the request body, since a client-supplied staff_id would be spoofable.
    """
    decoded = verify_qr_token(payload.token)
    if decoded is None or decoded.get("sid") != str(school.id):
        raise HTTPException(status_code=400, detail="Invalid QR code")

    credential = (
        tenant_db.query(QRCredential)
        .filter_by(token=payload.token, revoked_at=None)
        .first()
    )
    if credential is None:
        raise HTTPException(status_code=400, detail="This QR code is unrecognized or has been revoked")

    student = tenant_db.get(Student, payload.student_id)
    student_name = student.name if student is not None else "A child"

    link = (
        tenant_db.query(GuardianStudentLink)
        .filter_by(
            guardian_id=credential.guardian_id,
            student_id=payload.student_id,
            is_authorized_pickup=True,
        )
        .first()
    )
    if link is None:
        flagged_event = AttendanceEvent(
            student_id=payload.student_id,
            guardian_id=credential.guardian_id,
            type=payload.type,
            scanned_by_staff_id=staff["sub"],
            flagged=True,
            flag_reason="guardian_not_authorized_for_student",
        )
        tenant_db.add(flagged_event)
        tenant_db.commit()

        # ARCHITECTURE.md §6: unauthorized attempt -> alert real guardians,
        # not the person who scanned (they aren't one of them).
        real_guardians = _guardians_for_student(tenant_db, payload.student_id)
        _push_to_guardians(
            tenant_db,
            real_guardians,
            flagged_event.id,
            title=f"Unrecognized attempt for {student_name}",
            body=(
                f"Someone scanned an unrecognized/unauthorized code for {student_name} at {school.name}. "
                "If this wasn't expected, please contact the school right away."
            ),
        )
        raise HTTPException(status_code=403, detail="This guardian is not authorized for this child")

    event = AttendanceEvent(
        student_id=payload.student_id,
        guardian_id=credential.guardian_id,
        type=payload.type,
        scanned_by_staff_id=staff["sub"],
    )
    tenant_db.add(event)
    tenant_db.commit()

    # ARCHITECTURE.md §5 point 5: notify *all* guardians linked to this
    # child, not just the one who scanned — turns every other guardian into
    # a passive fraud detector.
    scanning_guardian = tenant_db.get(Guardian, credential.guardian_id)
    guardian_name = scanning_guardian.name if scanning_guardian is not None else "A guardian"
    action_label = _ACTION_LABEL.get(payload.type, payload.type)
    guardians = _guardians_for_student(tenant_db, payload.student_id)
    _push_to_guardians(
        tenant_db,
        guardians,
        event.id,
        title=f"{student_name} {action_label}",
        body=f"{student_name} was {action_label} by {guardian_name} at {school.name}.",
    )

    return {"event_id": event.id, "status": "recorded", "flagged": False}
