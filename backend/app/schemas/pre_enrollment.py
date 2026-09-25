import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PreEnrollmentInquiryRequest(BaseModel):
    school_name: str = Field(min_length=1, max_length=255)
    school_address: str = Field(min_length=1, max_length=500)
    contact_name: str = Field(min_length=1, max_length=255)
    contact_email: EmailStr
    contact_whatsapp: str = Field(min_length=1, max_length=30)
    active_parents_estimate: str = Field(min_length=1, max_length=100)
    desired_enrollment_date: str = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class PreEnrollmentInquiryOut(BaseModel):
    id: uuid.UUID
    school_name: str
    school_address: str
    contact_name: str
    contact_email: str
    contact_whatsapp: str
    active_parents_estimate: str
    desired_enrollment_date: str
    notes: str | None
    created_at: datetime

    class Config:
        from_attributes = True
