import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_school, get_tenant_db
from app.core.email import send_email
from app.core.qr_pdf import generate_qr_credential_pdf
from app.core.security import generate_qr_token
from app.db.platform import get_platform_db
from app.models.platform import GuardianMembership, PlatformUser, School
from app.models.tenant import Guardian, QRCredential
from app.schemas.guardian import GuardianCreateRequest, GuardianOut

router = APIRouter(prefix="/guardians", tags=["guardians"])

_INVITE_TOKEN_VALIDITY = timedelta(days=7)


@router.post("", response_model=GuardianOut, status_code=201)
def create_guardian(
    payload: GuardianCreateRequest,
    school: School = Depends(get_school),
    platform_db: Session = Depends(get_platform_db),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    """School-initiated enrollment (ARCHITECTURE.md §8): staff creates the
    guardian record and prints their QR credential here; the parent's own
    account activation is a separate, later step and isn't required for
    this to work.

    Note: this writes to two separate physical databases (platform_db for
    the identity + membership rows, tenant_db for the guardian + QR
    credential) with two separate commits below — there's no cross-database
    transaction, so a crash between the two commits can leave them
    inconsistent. Acceptable for this scaffold; a production version should
    reconcile via a background job or outbox pattern.
    """
    platform_user = platform_db.query(PlatformUser).filter_by(email=payload.email).first()
    if platform_user is None:
        # Brand-new parent identity: issue an activation invite so they can
        # eventually log in (see /auth/parent/activate). An existing parent
        # (e.g. enrolling a second child, or one already at another school)
        # keeps whatever credentials/invite they already have — we don't
        # resend or reset it here.
        invite_token = secrets.token_urlsafe(24)
        platform_user = PlatformUser(
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            invite_token=invite_token,
            invite_token_expires_at=datetime.now(timezone.utc) + _INVITE_TOKEN_VALIDITY,
        )
        platform_db.add(platform_user)
        platform_db.flush()

        send_email(
            to_email=payload.email,
            subject=f"Activate your {school.name} attendance account",
            body=(
                f"{school.name} has added you as a guardian in the attendance app.\n\n"
                f"To activate your account, open the app and enter:\n"
                f"  Email: {payload.email}\n"
                f"  Activation code: {invite_token}\n\n"
                "This code expires in 7 days."
            ),
        )

    guardian = Guardian(
        platform_user_id=platform_user.id,
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
    )
    tenant_db.add(guardian)
    tenant_db.flush()

    token = generate_qr_token(guardian_id=str(guardian.id), school_id=str(school.id))
    tenant_db.add(QRCredential(guardian_id=guardian.id, token=token))
    tenant_db.commit()

    platform_db.add(
        GuardianMembership(
            platform_user_id=platform_user.id,
            school_id=school.id,
            tenant_guardian_id=guardian.id,
        )
    )
    platform_db.commit()

    return {"id": guardian.id, "name": guardian.name, "qr_token": token}


@router.get("/{guardian_id}/qr-credential.pdf")
def download_qr_credential_pdf(
    guardian_id: uuid.UUID,
    school: School = Depends(get_school),
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> Response:
    """The printed handout from ARCHITECTURE.md §8/§5 — staff prints this
    directly from the enrollment screen. Renders the guardian's most
    recent non-revoked QR credential; deliberately excludes any children's
    names or photos (see app/core/qr_pdf.py).
    """
    guardian = tenant_db.get(Guardian, guardian_id)
    if guardian is None:
        raise HTTPException(status_code=404, detail="Unknown guardian")

    credential = (
        tenant_db.query(QRCredential)
        .filter_by(guardian_id=guardian_id, revoked_at=None)
        .order_by(QRCredential.issued_at.desc())
        .first()
    )
    if credential is None:
        raise HTTPException(status_code=404, detail="This guardian has no active QR credential")

    pdf_bytes = generate_qr_credential_pdf(
        guardian_name=guardian.name,
        school_name=school.name,
        qr_token=credential.token,
    )
    filename = f"{guardian.name.replace(' ', '_')}-qr-credential.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
