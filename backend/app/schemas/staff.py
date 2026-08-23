import uuid

from pydantic import BaseModel, ConfigDict, Field


class StaffAccountCreateRequest(BaseModel):
    # Deliberately a plain string, not EmailStr — the spec calls this a
    # "username", not necessarily an email address (unlike the School
    # Admin's own login, which is created by the Master Admin as an email).
    username: str = Field(min_length=3)
    password: str = Field(min_length=8)


class StaffAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str
