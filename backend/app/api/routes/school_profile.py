"""A School's own self-service branding — separate from the Master-Admin-only
`PATCH /platform/schools/{id}` in schools.py. Lets a School Admin see and set
their own school's name/logo, used by the School Admin console header
(app/static/school_admin/index.html) and printed on guardian QR credential
cards (app/core/qr_pdf.py).
"""

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.api.deps import get_current_staff, get_school, require_school_admin
from app.db.platform import get_platform_db
from app.models.platform import School
from app.schemas.school import SchoolProfileOut
from sqlalchemy.orm import Session

router = APIRouter(prefix="/school", tags=["school-profile"], dependencies=[Depends(get_current_staff)])

_ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2MB — plenty for a logo, small enough to sit in a DB row.


@router.get("/me", response_model=SchoolProfileOut)
def get_my_school(school: School = Depends(get_school)) -> dict:
    """Powers the School Admin console header — name + whether a logo has
    been uploaded (fetch the actual image separately via GET /school/logo,
    same pattern the console already uses for QR credential PDFs: a second
    request for the binary body rather than inlining it here as base64).
    """
    return {"name": school.name, "has_logo": school.logo is not None}


@router.get("/logo")
def get_school_logo(school: School = Depends(get_school)) -> Response:
    if school.logo is None:
        raise HTTPException(status_code=404, detail="This school hasn't uploaded a logo")
    return Response(content=school.logo, media_type=school.logo_content_type or "application/octet-stream")


@router.post("/logo", dependencies=[Depends(require_school_admin)])
async def upload_school_logo(
    file: UploadFile = File(...),
    school: School = Depends(get_school),
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    if file.content_type not in _ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=422, detail="Logo must be a PNG, JPEG, or WEBP image")

    data = await file.read()
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(status_code=422, detail="Logo must be smaller than 2MB")

    school.logo = data
    school.logo_content_type = file.content_type
    platform_db.commit()
    return {"ok": True}


@router.delete("/logo", dependencies=[Depends(require_school_admin)])
def delete_school_logo(
    school: School = Depends(get_school),
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    school.logo = None
    school.logo_content_type = None
    platform_db.commit()
    return {"ok": True}
