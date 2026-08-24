import uuid
import zoneinfo
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SchoolEnrollRequest(BaseModel):
    name: str
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,60}$", description="Used to build the tenant DB name and as the X-School-Slug header value")
    address: str
    phone: str
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
    sequence_no: int
    name: str
    slug: str
    address: str | None
    phone: str | None
    status: str
    timezone: str
    billing_email: str | None
    archived_at: datetime | None = None


class SchoolWithSubscriptionOut(BaseModel):
    id: uuid.UUID
    sequence_no: int
    name: str
    slug: str
    status: str
    timezone: str
    billing_email: str | None
    created_at: datetime
    subscription_status: str
    archived_at: datetime | None = None


class SchoolDetailOut(BaseModel):
    """Backs the Master Admin console's per-school detail view: child count
    + current billing-period window, neither of which exist on the plain
    School/Subscription rows — child count is a live tenant-DB count, and
    the period window is derived from Subscription.started_at plus the
    latest Invoice, if any (see GET /platform/schools/{id}).
    """

    id: uuid.UUID
    sequence_no: int
    name: str
    slug: str
    address: str | None
    phone: str | None
    timezone: str
    billing_email: str | None
    subscription_status: str
    started_at: datetime
    current_period_start: date
    current_period_end: date
    child_count: int
    archived_at: datetime | None = None


class SchoolUpdateRequest(BaseModel):
    """Partial update — only fields actually present in the request body are
    changed (see model_dump(exclude_unset=True) in the route). `slug` is
    deliberately not editable here: it's the tenant-DB routing key baked
    into the school's own database name at enrollment time.
    """

    name: str | None = None
    address: str | None = None
    phone: str | None = None
    billing_email: EmailStr | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            zoneinfo.ZoneInfo(value)
        except zoneinfo.ZoneInfoNotFoundError:
            raise ValueError(f"Unknown IANA timezone: {value!r}")
        return value
