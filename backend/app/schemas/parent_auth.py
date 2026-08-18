from pydantic import BaseModel, EmailStr, Field


class ParentActivateRequest(BaseModel):
    email: EmailStr
    invite_token: str
    password: str = Field(min_length=8)


class ParentLoginRequest(BaseModel):
    email: EmailStr
    password: str


class ParentTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
