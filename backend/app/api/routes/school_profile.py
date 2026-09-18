"""A School's own view of its profile — read-only. Setting/removing the
logo is Master-Admin-only now (POST/DELETE /platform/schools/{id}/logo in
schools.py); a School Admin can see what's been uploaded, via the School
Admin console header (app/static/school_admin/index.html) and on printed
guardian QR credential cards (app/core/qr_pdf.py), but can't change it.
"""

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import get_current_staff, get_school
from app.models.platform import School
from app.schemas.school import SchoolProfileOut

router = APIRouter(prefix="/school", tags=["school-profile"], dependencies=[Depends(get_current_staff)])


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
