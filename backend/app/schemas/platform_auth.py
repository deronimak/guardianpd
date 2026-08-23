from pydantic import BaseModel, EmailStr


class PlatformStaffLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PlatformStaffTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
