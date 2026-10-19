import datetime as dt
import logging
import zoneinfo

import firebase_admin.exceptions
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_tenant_db, require_active_subscription
from app.core.push import send_push
from app.core.sms import send_sms
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
from app.schemas.attendance import (
    GuardianScanBatchRequest,
    GuardianScanBatchResponse,
    GuardianScanResult,
    ScanRequest,
    ScanResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance", tags=["attendance"])

_ACTION_LABEL = {"drop_off": "dropped off", "pick_up": "picked up"}


def _guardians_for_student(tenant_db: Session, student_id) -> list[Guardian]:
    return (
        tenant_db.query(Guardian)
        .join(GuardianStudentLink, GuardianStudentLink.guardian_id == Guardian.id)
        .filter(GuardianStudentLink.student_id == student_id)
        .all()
    )


def _push_to_guardians(
    tenant_db: Session,
    guardians: list[Guardian],
    event_id,
    title: str,
    body: str,
    school: School | None = None,
    sms_text: str | None = None,
) -> None:
    """Best-effort: a bad/stale device token must never fail the attendance
    write itself — the scan already succeeded before this runs. A dead
    token (app uninstalled, etc.) is pruned; any other send error is just
    logged so one broken token can't block everyone else's notification.
    """
    for guardian in guardians:
        devices = tenant_db.query(GuardianDeviceToken).filter_by(guardian_id=guardian.id).all()
        for device in devices:
            try:
                send_push(device.token, title=title, body=body)
            except (firebase_admin.exceptions.NotFoundError, firebase_admin.exceptions.InvalidArgumentError):
                logger.info("Pruning dead device token for guardian %s", guardian.id)
                tenant_db.delete(device)
            except Exception:
                logger.exception("Push send failed for guardian %s (continuing)", guardian.id)
        # One Notification row per guardian even with zero devices registered
        # yet — keeps an auditable record that we tried, per ARCHITECTURE.md §7.
        tenant_db.add(Notification(guardian_id=guardian.id, event_id=event_id, channel="push"))

        # Opt-in per school (costs money): text only guardians who have no
        # phone registered for push, i.e. those the push above can't reach.
        if school is not None and school.sms_enabled and not devices and guardian.phone:
            try:
                if send_sms(guardian.phone, sms_text or body):
                    tenant_db.add(Notification(guardian_id=guardian.id, event_id=event_id, channel="sms"))
            except Exception:
                logger.exception("SMS send failed for guardian %s (continuing)", guardian.id)
    tenant_db.commit()


# Two scans of the same guardian/child/direction inside this window are one
# physical scan (a retried upload), not two events. Only applied to scans that
# carry their own timestamp (the offline batch), so live scans behave as before.
_DUPLICATE_WINDOW = dt.timedelta(seconds=90)
_FUTURE_SKEW = dt.timedelta(minutes=5)
_MAX_OFFLINE_AGE = dt.timedelta(days=3)
_LATE_NOTICE_AFTER = dt.timedelta(minutes=3)


def _local_time_label(school: School, when: dt.datetime) -> str:
    try:
        tz = zoneinfo.ZoneInfo(school.timezone)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        tz = dt.timezone.utc
    return when.astimezone(tz).strftime("%I:%M %p").lstrip("0")


def _record_guardian_scan(
    token: str,
    student_id,
    scan_type: str,
    school: School,
    staff_id,
    tenant_db: Session,
    when: dt.datetime | None = None,
) -> dict:
    """The core security-critical flow — ARCHITECTURE.md §5/§6, shared by the
    live scan and the offline batch upload.

    Order matters: signature check -> revocation check (DB) -> per-child
    authorization check (DB) -> write. scanned_by_staff_id comes from the
    authenticated staff JWT, never from the request body, since a
    client-supplied staff_id would be spoofable. `when` is the time the scan
    physically happened (offline uploads); None means "now". Raises
    HTTPException exactly as the live endpoint always has.
    """
    decoded = verify_qr_token(token)
    if decoded is None or decoded.get("sid") != str(school.id):
        raise HTTPException(status_code=400, detail="Invalid QR code")

    credential = tenant_db.query(QRCredential).filter_by(token=token, revoked_at=None).first()
    if credential is None:
        raise HTTPException(status_code=400, detail="This QR code is unrecognized or has been revoked")

    now = dt.datetime.now(dt.timezone.utc)
    if when is not None:
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        if when > now + _FUTURE_SKEW:
            raise HTTPException(status_code=400, detail="Scan time is in the future; check the phone's clock")
        when = min(when, now)
        if now - when > _MAX_OFFLINE_AGE:
            raise HTTPException(
                status_code=400, detail="Scan is too old to sync; please record it manually with the school office"
            )

        near = (
            tenant_db.query(AttendanceEvent)
            .filter(
                AttendanceEvent.student_id == student_id,
                AttendanceEvent.guardian_id == credential.guardian_id,
                AttendanceEvent.type == scan_type,
                AttendanceEvent.flagged.is_(False),
                AttendanceEvent.timestamp >= when - _DUPLICATE_WINDOW,
                AttendanceEvent.timestamp <= when + _DUPLICATE_WINDOW,
            )
            .first()
        )
        if near is not None:
            return {"event_id": near.id, "status": "duplicate", "flagged": False}

    late = when is not None and now - when > _LATE_NOTICE_AFTER
    late_note = f" at {_local_time_label(school, when)} (recorded earlier, delivered late)" if late else ""

    student = tenant_db.get(Student, student_id)
    student_name = student.name if student is not None else "A child"

    link = (
        tenant_db.query(GuardianStudentLink)
        .filter_by(guardian_id=credential.guardian_id, student_id=student_id, is_authorized_pickup=True)
        .first()
    )
    if link is None:
        flagged_event = AttendanceEvent(
            student_id=student_id,
            guardian_id=credential.guardian_id,
            type=scan_type,
            scanned_by_staff_id=staff_id,
            flagged=True,
            flag_reason="guardian_not_authorized_for_student",
            **({"timestamp": when} if when is not None else {}),
        )
        tenant_db.add(flagged_event)
        tenant_db.commit()

        # ARCHITECTURE.md §6: unauthorized attempt -> alert real guardians,
        # not the person who scanned (they aren't one of them).
        real_guardians = _guardians_for_student(tenant_db, student_id)
        _push_to_guardians(
            tenant_db,
            real_guardians,
            flagged_event.id,
            title=f"Unrecognized attempt for {student_name}",
            body=(
                f"Someone scanned an unrecognized/unauthorized code for {student_name}{late_note} at {school.name}. "
                "If this wasn't expected, please contact the school right away."
            ),
            school=school,
            sms_text=f"{school.name}: an unrecognized code was scanned for {student_name}{late_note}. If unexpected, contact the school.",
        )
        raise HTTPException(status_code=403, detail="This guardian is not authorized for this child")

    event = AttendanceEvent(
        student_id=student_id,
        guardian_id=credential.guardian_id,
        type=scan_type,
        scanned_by_staff_id=staff_id,
        **({"timestamp": when} if when is not None else {}),
    )
    tenant_db.add(event)
    tenant_db.commit()

    # ARCHITECTURE.md §5 point 5: notify *all* guardians linked to this
    # child, not just the one who scanned — turns every other guardian into
    # a passive fraud detector.
    scanning_guardian = tenant_db.get(Guardian, credential.guardian_id)
    guardian_name = scanning_guardian.name if scanning_guardian is not None else "A guardian"
    action_label = _ACTION_LABEL.get(scan_type, scan_type)
    guardians = _guardians_for_student(tenant_db, student_id)
    _push_to_guardians(
        tenant_db,
        guardians,
        event.id,
        title=f"{student_name} {action_label}",
        body=f"{student_name} was {action_label} by {guardian_name}{late_note} at {school.name}.",
        school=school,
    )

    return {"event_id": event.id, "status": "recorded", "flagged": False}


@router.post("/scan", response_model=ScanResponse)
def scan_qr(
    payload: ScanRequest,
    school: School = Depends(require_active_subscription),
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    return _record_guardian_scan(payload.token, payload.student_id, payload.type, school, staff["sub"], tenant_db)


@router.post("/scan/batch", response_model=GuardianScanBatchResponse)
def scan_qr_batch(
    payload: GuardianScanBatchRequest,
    school: School = Depends(require_active_subscription),
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> GuardianScanBatchResponse:
    """Upload guardian scans saved on a phone while it had no signal. Each
    scan is checked exactly like a live one (signature, revocation, the
    guardian's authorization for that child), using the time it really
    happened. Results come back in request order, one per scan: "recorded",
    "duplicate" (already uploaded), "flagged" (guardian not authorized for
    that child — the real guardians are alerted, as live), or "rejected".
    """
    now = dt.datetime.now(dt.timezone.utc)

    def when_of(index: int) -> dt.datetime:
        when = payload.scans[index].scanned_at or now
        return when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)

    results: list[GuardianScanResult | None] = [None] * len(payload.scans)
    for index in sorted(range(len(payload.scans)), key=when_of):
        item = payload.scans[index]
        try:
            outcome = _record_guardian_scan(
                item.token, item.student_id, item.type, school, staff["sub"], tenant_db, when=when_of(index)
            )
            results[index] = GuardianScanResult(status=outcome["status"], event_id=outcome["event_id"])
        except HTTPException as exc:
            tenant_db.rollback()
            results[index] = GuardianScanResult(
                status="flagged" if exc.status_code == 403 else "rejected", detail=str(exc.detail)
            )
    return GuardianScanBatchResponse(results=results)  # type: ignore[arg-type]
