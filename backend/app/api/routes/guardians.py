import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_school, get_tenant_db, require_school_admin
from app.core.email import send_email
from app.core.qr_pdf import generate_qr_credential_pdf
from app.core.security import generate_qr_token, verify_qr_token
from app.db.platform import get_platform_db
from app.db.twophase import get_twophase_session
from app.models.platform import GuardianMembership, PlatformUser, School
from app.models.tenant import Guardian, GuardianStudentLink, QRCredential, Student
from app.schemas.guardian import (
    GuardianCreateRequest,
    GuardianLookupOut,
    GuardianOut,
    GuardianSummaryOut,
)

router = APIRouter(prefix="/guardians", tags=["guardians"], dependencies=[Depends(get_current_staff)])

_INVITE_TOKEN_VALIDITY = timedelta(days=7)


def _activation_email(school_name: str, email: str, invite_token: str) -> None:
    send_email(
        to_email=email,
        subject=f"Activate your {school_name} attendance account",
        body=(
            f"{school_name} has added you as a guardian in the attendance app.\n\n"
            f"To activate your account, open the app and enter:\n"
            f"  Email: {email}\n"
            f"  Activation code: {invite_token}\n\n"
            "This code expires in 7 days."
        ),
    )


@router.post("", response_model=GuardianOut, status_code=201, dependencies=[Depends(require_school_admin)])
def create_guardian(
    payload: GuardianCreateRequest,
    school: School = Depends(get_school),
) -> dict:
    """School-Admin-initiated combined enrollment (GuardianPD spec): creates
    the guardian, their printed QR credential, and up to 10 named children
    in one atomic transaction — replacing the old two-step "create guardian"
    then "link to student" flow as the primary enrollment path (that flow
    still exists at POST /students + POST /students/{id}/guardians/{id} for
    linking an *existing* guardian to an *additional* already-enrolled
    student later).

    Writes to two physical databases (platform_db for the identity +
    membership rows, tenant_db for the guardian/children/QR credential) as a
    single atomic unit via two-phase commit (app/db/twophase.py) — either
    everything exists or nothing does. The invite email is sent only after
    commit succeeds, so a parent never gets an activation code for a
    guardian record that didn't actually get created.
    """
    db = get_twophase_session(school.tenant_db_name)
    try:
        platform_user = db.query(PlatformUser).filter_by(email=payload.email).first()
        invite_token: str | None = None
        if platform_user is None:
            # Brand-new parent identity: issue an activation invite so they
            # can eventually log in (see /auth/parent/activate). An existing
            # parent (e.g. enrolling a second child, or one already at
            # another school) keeps whatever credentials/invite they
            # already have — use "resend activation" to reissue one.
            invite_token = secrets.token_urlsafe(24)
            platform_user = PlatformUser(
                name=payload.name,
                email=payload.email,
                phone=payload.phone,
                invite_token=invite_token,
                invite_token_expires_at=datetime.now(timezone.utc) + _INVITE_TOKEN_VALIDITY,
            )
            db.add(platform_user)
            db.flush()

        guardian = Guardian(
            platform_user_id=platform_user.id,
            name=payload.name,
            phone=payload.phone,
            email=payload.email,
        )
        db.add(guardian)
        db.flush()

        token = generate_qr_token(guardian_id=str(guardian.id), school_id=str(school.id))
        db.add(QRCredential(guardian_id=guardian.id, token=token))
        db.add(
            GuardianMembership(
                platform_user_id=platform_user.id,
                school_id=school.id,
                tenant_guardian_id=guardian.id,
            )
        )

        children_out = []
        for child in payload.children:
            student = Student(name=child.name)
            db.add(student)
            db.flush()
            db.add(GuardianStudentLink(guardian_id=guardian.id, student_id=student.id))
            children_out.append({"id": student.id, "name": student.name, "grade": None})

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if invite_token is not None:
        _activation_email(school.name, payload.email, invite_token)

    return {"id": guardian.id, "name": guardian.name, "qr_token": token, "children": children_out}


@router.get("", response_model=list[GuardianSummaryOut], dependencies=[Depends(require_school_admin)])
def search_guardians(query: str | None = None, tenant_db: Session = Depends(get_tenant_db)) -> list[Guardian]:
    """Backs the School Admin "search guardians" screen — print QR
    credentials and resend activation links both start here.
    """
    q = tenant_db.query(Guardian)
    if query:
        like = f"%{query}%"
        q = q.filter(
            (Guardian.name.ilike(like)) | (Guardian.email.ilike(like)) | (Guardian.phone.ilike(like))
        )
    return q.order_by(Guardian.name).all()


@router.post("/{guardian_id}/resend-activation", dependencies=[Depends(require_school_admin)])
def resend_activation(
    guardian_id: uuid.UUID,
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    """Regenerates and resends the activation invite — the original
    create_guardian flow only ever sends this once, and there was
    previously no way to get another copy if a guardian lost the email or
    the code expired.
    """
    guardian = tenant_db.get(Guardian, guardian_id)
    if guardian is None:
        raise HTTPException(status_code=404, detail="Unknown guardian")

    platform_user = platform_db.get(PlatformUser, guardian.platform_user_id)
    if platform_user is None:
        raise HTTPException(status_code=404, detail="No parent account found for this guardian")
    if platform_user.password_hash is not None:
        raise HTTPException(status_code=409, detail="This guardian has already activated their account")

    invite_token = secrets.token_urlsafe(24)
    platform_user.invite_token = invite_token
    platform_user.invite_token_expires_at = datetime.now(timezone.utc) + _INVITE_TOKEN_VALIDITY
    platform_db.commit()

    _activation_email(school.name, platform_user.email, invite_token)
    return {"status": "sent"}


@router.get("/lookup", response_model=GuardianLookupOut)
def lookup_guardian_by_qr(
    token: str,
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    """Powers the staff scanner's student picker (ARCHITECTURE.md §6): after
    a QR scan, staff need to see which children this guardian is actually
    authorized to drop off/pick up before recording an attendance event —
    this is that lookup, done before POST /attendance/scan rather than by
    listing every student at the school. Reachable by School Staff *and*
    School Admin (unlike the routes above) since scanning is staff's job.

    Mirrors the same signature/revocation checks as the scan endpoint, but
    this alone is NOT an attendance record — POST /attendance/scan
    independently re-verifies authorization for whichever student staff
    picks, so a stale/mismatched lookup result can't be used to bypass it.
    """
    decoded = verify_qr_token(token)
    if decoded is None or decoded.get("sid") != str(school.id):
        raise HTTPException(status_code=400, detail="Invalid QR code")

    credential = tenant_db.query(QRCredential).filter_by(token=token, revoked_at=None).first()
    if credential is None:
        raise HTTPException(status_code=400, detail="This QR code is unrecognized or has been revoked")

    guardian = tenant_db.get(Guardian, credential.guardian_id)
    if guardian is None:
        raise HTTPException(status_code=404, detail="Unknown guardian")

    students = (
        tenant_db.query(Student)
        .join(GuardianStudentLink, GuardianStudentLink.student_id == Student.id)
        .filter(GuardianStudentLink.guardian_id == guardian.id, GuardianStudentLink.is_authorized_pickup)
        .all()
    )
    return {"guardian_id": guardian.id, "guardian_name": guardian.name, "students": students}


@router.get("/{guardian_id}/qr-credential.pdf", dependencies=[Depends(require_school_admin)])
def download_qr_credential_pdf(
    guardian_id: uuid.UUID,
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
) -> Response:
    """The printed handout from ARCHITECTURE.md §8/§5 — School Admin prints
    this from the enroll/search screens (mobile and web). Renders the
    guardian's most recent non-revoked QR credential plus the names of
    every child linked to them (see app/core/qr_pdf.py).
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

    children_names = [
        row.name
        for row in tenant_db.query(Student.name)
        .join(GuardianStudentLink, GuardianStudentLink.student_id == Student.id)
        .filter(GuardianStudentLink.guardian_id == guardian_id)
        .order_by(Student.name)
        .all()
    ]

    pdf_bytes = generate_qr_credential_pdf(
        guardian_name=guardian.name,
        school_name=school.name,
        qr_token=credential.token,
        children_names=children_names,
    )
    filename = f"{guardian.name.replace(' ', '_')}-qr-credential.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
