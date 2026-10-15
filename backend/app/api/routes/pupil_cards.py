"""Printing and reissuing pupil ID cards (School.credential_mode == "pupil").

School Admin only. Credentials are created lazily the first time a pupil's
card is printed, so switching a school to pupil mode needs no bulk
migration and enrolling a pupil needs no extra step.
"""

import datetime as dt
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_school, get_tenant_db, require_active_subscription, require_school_admin
from app.core.audit import record_audit, resolve_staff_actor_label
from app.core.qr_pdf import generate_pupil_cards_pdf
from app.core.security import generate_pupil_token
from app.models.platform import School
from app.api.routes.guardians import _activation_email, enroll_guardian
from app.api.routes.pupil_scan import _school_tz
from app.models.tenant import AttendanceEvent, Guardian, GuardianStudentLink, StaffUser, Student, StudentCredential
from app.schemas.guardian import ChildCreate, GuardianCreateRequest

_MAX_PHOTO_UPLOAD_BYTES = 8 * 1024 * 1024  # a raw phone photo; stored size is far smaller (see below).
_PHOTO_SIZE = (320, 400)  # 4:5 portrait, ~2.5x the printed size for a crisp card.

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
                "has_photo": student.photo is not None,
                "has_card": cred is not None,
                "print_count": cred.print_count if cred else 0,
                "last_printed_at": cred.last_printed_at if cred else None,
            }
        )
    return rows


@router.get("/attendance")
def pupil_attendance(
    day: dt.date | None = None,
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    """One school day of pupil attendance (the school's own local day; today
    by default): every pupil with when they arrived and when they left, who
    scanned them, and who hasn't arrived yet.
    """
    _require_pupil_mode(school)
    tz = _school_tz(school)
    the_day = day or dt.datetime.now(tz).date()
    start = dt.datetime.combine(the_day, dt.time.min, tzinfo=tz)
    end = dt.datetime.combine(the_day + dt.timedelta(days=1), dt.time.min, tzinfo=tz)

    events = (
        tenant_db.query(AttendanceEvent)
        .filter(
            AttendanceEvent.flagged.is_(False),
            AttendanceEvent.timestamp >= start.astimezone(dt.timezone.utc),
            AttendanceEvent.timestamp < end.astimezone(dt.timezone.utc),
        )
        .order_by(AttendanceEvent.timestamp)
        .all()
    )
    staff = {
        sid: name
        for sid, name in tenant_db.query(StaffUser.id, StaffUser.name)
        .filter(StaffUser.id.in_({e.scanned_by_staff_id for e in events} or {uuid.uuid4()}))
        .all()
    }

    def stamp(event: AttendanceEvent | None) -> tuple[str | None, str | None, str | None]:
        if event is None:
            return None, None, None
        local = event.timestamp.astimezone(tz)
        return event.timestamp.isoformat(), local.strftime("%I:%M %p").lstrip("0"), staff.get(event.scanned_by_staff_id)

    arrived: dict = {}
    left: dict = {}
    for event in events:
        if event.type == "drop_off":
            arrived.setdefault(event.student_id, event)
        else:
            left[event.student_id] = event

    rows = []
    for student in tenant_db.query(Student).order_by(Student.grade, Student.name).all():
        a_iso, a_time, a_by = stamp(arrived.get(student.id))
        l_iso, l_time, l_by = stamp(left.get(student.id))
        rows.append(
            {
                "student_id": student.id,
                "name": student.name,
                "grade": student.grade,
                "status": "left" if l_iso else ("present" if a_iso else "not_arrived"),
                "arrived_at": a_iso,
                "arrived_time": a_time,
                "arrived_by": a_by,
                "left_at": l_iso,
                "left_time": l_time,
                "left_by": l_by,
            }
        )
    return {
        "date": the_day.isoformat(),
        "total": len(rows),
        "arrived": sum(r["status"] != "not_arrived" for r in rows),
        "left": sum(r["status"] == "left" for r in rows),
        "not_arrived": sum(r["status"] == "not_arrived" for r in rows),
        "rows": rows,
    }


@router.get("/bulk.pdf")
def download_bulk_cards(
    grade: str | None = None,
    ids: str | None = None,
    school: School = Depends(require_active_subscription),
    tenant_db: Session = Depends(get_tenant_db),
) -> Response:
    """All pupils (or one class via ?grade=, or specific pupils via
    ?ids=a,b,c) in one PDF, front+back page per pupil, ready to feed through
    the card printer in one run."""
    _require_pupil_mode(school)
    query = tenant_db.query(Student).order_by(Student.grade, Student.name)
    if grade:
        query = query.filter(Student.grade == grade)
    if ids:
        try:
            wanted = [uuid.UUID(part) for part in ids.split(",") if part.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid pupil id list")
        query = query.filter(Student.id.in_(wanted))
    students = query.all()
    if not students:
        raise HTTPException(status_code=404, detail="No pupils to print")

    now = datetime.now(timezone.utc)
    pupils = []
    for student in students:
        credential = _active_credential(tenant_db, school, student)
        credential.print_count += 1
        credential.last_printed_at = now
        pupils.append(
            {"name": student.name, "grade": student.grade, "qr_token": credential.token, "photo": student.photo}
        )
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
        [{"name": student.name, "grade": student.grade, "qr_token": credential.token, "photo": student.photo}],
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


def _normalize_photo(data: bytes) -> bytes:
    """Any phone/camera photo -> a small portrait JPEG: honours the camera's
    rotation flag, centre-crops to 4:5 (biased towards the top so a head-and-
    shoulders shot keeps the face), downsizes and recompresses. Keeps the DB
    row small and the printed result consistent regardless of what was sent.
    """
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="That file isn't a readable image (use a JPG or PNG photo)")
    image = ImageOps.fit(image, _PHOTO_SIZE, method=Image.LANCZOS, centering=(0.5, 0.3))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


@router.put("/{student_id}/photo")
async def upload_pupil_photo(
    student_id: uuid.UUID,
    file: UploadFile = File(...),
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
) -> dict:
    _require_pupil_mode(school)
    student = tenant_db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Unknown pupil")
    data = await file.read(_MAX_PHOTO_UPLOAD_BYTES + 1)
    if len(data) > _MAX_PHOTO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Photo is too large (max 8MB)")
    student.photo = _normalize_photo(data)
    tenant_db.commit()
    return {"student_id": student_id, "has_photo": True}


@router.get("/{student_id}/photo")
def get_pupil_photo(
    student_id: uuid.UUID,
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
) -> Response:
    _require_pupil_mode(school)
    student = tenant_db.get(Student, student_id)
    if student is None or student.photo is None:
        raise HTTPException(status_code=404, detail="No photo for this pupil")
    return Response(content=student.photo, media_type="image/jpeg")


class ImportRow(BaseModel):
    pupil_name: str
    grade: str | None = None
    # Optional: with a guardian, the parent is enrolled (or linked, if already
    # at this school) so they get arrival/departure alerts. Without one, the
    # pupil is still created and can be scanned.
    guardian_name: str | None = None
    guardian_email: str | None = None
    guardian_phone: str | None = None


class ImportRequest(BaseModel):
    rows: list[ImportRow] = Field(max_length=500)


_email_adapter = TypeAdapter(EmailStr)


@router.post("/import")
def import_pupils(
    payload: ImportRequest,
    school: School = Depends(get_school),
    tenant_db: Session = Depends(get_tenant_db),
    claims: dict = Depends(get_current_staff),
) -> dict:
    """Bulk-enroll pupils (and their parents) from a spreadsheet the browser
    has already parsed. Safe to re-run with the same file: a pupil whose
    name+class already exists is reported "exists" and left alone, and a
    parent whose email is already a guardian here is linked to rather than
    duplicated. Each parent's family is created atomically; a bad row never
    blocks the others.
    """
    _require_pupil_mode(school)
    actor = resolve_staff_actor_label(tenant_db, claims)

    def key(name: str, grade: str | None) -> tuple[str, str]:
        return (" ".join(name.lower().split()), (grade or "").strip().lower())

    existing_pupils = {key(s.name, s.grade) for s in tenant_db.query(Student).all()}
    guardians_by_email = {
        g.email.lower(): g.id for g in tenant_db.query(Guardian).filter(Guardian.email.isnot(None)).all()
    }

    results: dict[int, dict] = {}
    # guardian email -> [(row_no, ImportRow)] for rows still to create
    families: dict[str, list[tuple[int, ImportRow]]] = {}
    loose: list[tuple[int, ImportRow]] = []
    seen: set[tuple[str, str]] = set()

    for number, row in enumerate(payload.rows, start=1):
        name = " ".join(row.pupil_name.split())
        grade = (row.grade or "").strip() or None
        if not name:
            results[number] = {"row": number, "status": "error", "detail": "Pupil name is empty"}
            continue
        k = key(name, grade)
        if k in existing_pupils or k in seen:
            results[number] = {"row": number, "status": "exists", "detail": "Already enrolled"}
            continue
        seen.add(k)
        row = row.model_copy(update={"pupil_name": name, "grade": grade})

        email = (row.guardian_email or "").strip()
        if not email:
            loose.append((number, row))
            continue
        try:
            email = str(_email_adapter.validate_python(email)).lower()
        except ValidationError:
            results[number] = {"row": number, "status": "error", "detail": f"Invalid parent email: {email}"}
            continue
        if not (row.guardian_name or "").strip():
            results[number] = {"row": number, "status": "error", "detail": "Parent name is required with a parent email"}
            continue
        families.setdefault(email, []).append((number, row))

    def add_pupil(row: ImportRow) -> Student:
        student = Student(name=row.pupil_name, grade=row.grade)
        tenant_db.add(student)
        tenant_db.flush()
        record_audit(tenant_db, "student", student.id, "created", f"Imported pupil {student.name}", actor)
        return student

    for number, row in loose:
        try:
            add_pupil(row)
            tenant_db.commit()
            results[number] = {"row": number, "status": "created"}
        except Exception as exc:
            tenant_db.rollback()
            results[number] = {"row": number, "status": "error", "detail": str(exc)[:120]}

    for email, members in families.items():
        try:
            if email in guardians_by_email:
                for number, row in members:
                    student = add_pupil(row)
                    tenant_db.add(GuardianStudentLink(guardian_id=guardians_by_email[email], student_id=student.id))
                tenant_db.commit()
                invite = None
            else:
                first = members[0][1]
                _, invite = enroll_guardian(
                    school,
                    claims,
                    GuardianCreateRequest(
                        name=first.guardian_name.strip(),
                        email=email,
                        phone=(first.guardian_phone or "").strip() or None,
                        children=[ChildCreate(name=r.pupil_name, grade=r.grade) for _, r in members],
                    ),
                )
                if invite is not None:
                    _activation_email(school.name, email, invite)
            for number, _ in members:
                results[number] = {"row": number, "status": "created"}
        except Exception as exc:
            tenant_db.rollback()
            detail = getattr(exc, "detail", None) or str(exc)
            for number, _ in members:
                results[number] = {"row": number, "status": "error", "detail": str(detail)[:120]}

    ordered = [results[n] for n in sorted(results)]
    return {
        "created": sum(r["status"] == "created" for r in ordered),
        "existing": sum(r["status"] == "exists" for r in ordered),
        "failed": sum(r["status"] == "error" for r in ordered),
        "rows": ordered,
    }
