import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class StudentCreateRequest(BaseModel):
    name: str
    dob: date | None = None
    grade: str | None = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class LinkCreateRequest(BaseModel):
    relationship: str | None = None
    is_authorized_pickup: bool = True
