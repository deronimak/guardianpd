from pydantic import BaseModel, Field


class StaffLoginRequest(BaseModel):
    # Plain str, not EmailStr — a School Admin's login is an email (set by
    # the Master Admin at enrollment), but a School Staff account's
    # "username" (POST /staff) isn't necessarily one.
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Lets the mobile client branch to the School Admin vs School Staff
    # home screen without decoding the JWT itself.
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
