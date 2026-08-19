import uuid

from pydantic import BaseModel, EmailStr


class GuardianCreateRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None


class GuardianOut(BaseModel):
    id: uuid.UUID
    name: str
    qr_token: str


class LinkedStudentOut(BaseModel):
    id: uuid.UUID
    name: str
    grade: str | None = None


class GuardianLookupOut(BaseModel):
    guardian_id: uuid.UUID
    guardian_name: str
    students: list[LinkedStudentOut]
