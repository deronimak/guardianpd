import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SchoolEnrollRequest(BaseModel):
    name: str
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,60}$", description="Used to build the tenant DB name and as the X-School-Slug header value")
    admin_name: str
    admin_email: EmailStr
    admin_temp_password: str = Field(min_length=8)


class SchoolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
