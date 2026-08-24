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
    dob: date | None = None
    grade: str | None = None


class StudentUpdateRequest(BaseModel):
    """Partial update for the Master Admin's child-search edit action — only
    fields actually present in the request body are changed (see
    model_dump(exclude_unset=True) in the route)."""

    name: str | None = None
    dob: date | None = None
    grade: str | None = None


class LinkCreateRequest(BaseModel):
    relationship: str | None = None
    is_authorized_pickup: bool = True
