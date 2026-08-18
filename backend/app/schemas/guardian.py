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
