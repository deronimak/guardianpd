from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_tenant_db, require_active_subscription
from app.core.security import verify_qr_token
from app.models.platform import School
from app.models.tenant import AttendanceEvent, GuardianStudentLink, QRCredential
from app.schemas.attendance import ScanRequest, ScanResponse

router = APIRouter(prefix="/attendance", tags=["attendance"])


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
        raise HTTPException(status_code=403, detail="This guardian is not authorized for this child")

    event = AttendanceEvent(
        student_id=payload.student_id,
        guardian_id=credential.guardian_id,
        type=payload.type,
        scanned_by_staff_id=staff["sub"],
    )
    tenant_db.add(event)
    tenant_db.commit()

    # TODO(ARCHITECTURE.md §5 point 5): fan out a real-time notification to
    # every guardian linked to this student, not just the one who scanned.
    # Not wired up yet — see README "What's scaffolded vs. not yet built".

    return {"event_id": event.id, "status": "recorded", "flagged": False}
