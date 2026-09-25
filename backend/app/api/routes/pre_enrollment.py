import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.email import send_email
from app.db.platform import get_platform_db
from app.models.platform import PreEnrollmentInquiry
from app.schemas.pre_enrollment import PreEnrollmentInquiryOut, PreEnrollmentInquiryRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pre-enrollment"])

_NOTIFY_EMAIL = "info@guardianpd.app"


@router.post("/pre-enrollment-inquiries", response_model=PreEnrollmentInquiryOut, status_code=201)
def submit_pre_enrollment_inquiry(
    payload: PreEnrollmentInquiryRequest,
    platform_db: Session = Depends(get_platform_db),
) -> PreEnrollmentInquiry:
    """Deliberately public — a prospective school has no account yet, so
    there's nothing to gate this on (ARCHITECTURE.md's auth model only
    covers schools that already exist). Submitted from the marketing site's
    pre-enrollment page and the standalone PDF form's contact instructions.
    """
    inquiry = PreEnrollmentInquiry(**payload.model_dump())
    platform_db.add(inquiry)
    platform_db.commit()
    platform_db.refresh(inquiry)

    try:
        send_email(
            to_email=_NOTIFY_EMAIL,
            subject=f"New pre-enrollment inquiry: {inquiry.school_name}",
            body=(
                f"School: {inquiry.school_name}\n"
                f"Address: {inquiry.school_address}\n\n"
                f"Contact: {inquiry.contact_name}\n"
                f"Email: {inquiry.contact_email}\n"
                f"WhatsApp: {inquiry.contact_whatsapp}\n\n"
                f"Estimated active parents: {inquiry.active_parents_estimate}\n"
                f"Desired enrollment date: {inquiry.desired_enrollment_date}\n\n"
                f"Notes: {inquiry.notes or '(none)'}\n"
            ),
        )
    except Exception:
        # The inquiry is already committed — a notification-email failure
        # shouldn't turn into a 500 for the prospect submitting the form.
        logger.exception("pre_enrollment: failed to send notification email for inquiry %s", inquiry.id)

    return inquiry
