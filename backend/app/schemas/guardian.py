import uuid

from pydantic import BaseModel, EmailStr, Field


class ChildCreate(BaseModel):
    name: str


class GuardianCreateRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    # Combined guardian+children enrollment (GuardianPD spec): a dropdown of
    # 1-10 on the mobile side maps to this list's length.
    children: list[ChildCreate] = Field(default_factory=list, max_length=10)


class LinkedStudentOut(BaseModel):
    id: uuid.UUID
    name: str
    grade: str | None = None


class GuardianOut(BaseModel):
    id: uuid.UUID
    name: str
    qr_token: str
    children: list[LinkedStudentOut] = Field(default_factory=list)


class GuardianSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    children: list[LinkedStudentOut] = Field(default_factory=list)


class GuardianUpdateRequest(BaseModel):
    """Partial update — only fields actually present in the request body are
    changed. Editing email also updates the guardian's shared PlatformUser
    login identity (see app/api/routes/guardians.py's update_guardian),
    since Guardian.email is a denormalized copy of it.
    """

    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class GuardianLookupOut(BaseModel):
    guardian_id: uuid.UUID
    guardian_name: str
    students: list[LinkedStudentOut]
