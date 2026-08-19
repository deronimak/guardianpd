import uuid
import zoneinfo
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SchoolEnrollRequest(BaseModel):
    name: str
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,60}$", description="Used to build the tenant DB name and as the X-School-Slug header value")
    admin_name: str
    admin_email: EmailStr
    admin_temp_password: str = Field(min_length=8)
    timezone: str = Field(default="UTC", description="IANA timezone identifier, e.g. 'America/New_York' — drives welfare-job cutoff times")
    billing_email: EmailStr | None = Field(default=None, description="Paystack checkout contact — defaults to admin_email if omitted")

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            zoneinfo.ZoneInfo(value)
        except zoneinfo.ZoneInfoNotFoundError:
            raise ValueError(f"Unknown IANA timezone: {value!r}")
        return value


class SchoolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    timezone: str
    billing_email: str | None


class SchoolWithSubscriptionOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    timezone: str
    billing_email: str | None
    created_at: datetime
    subscription_status: str
    subscription_plan: str
