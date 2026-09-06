from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.platform import get_platform_db
from app.models.platform import PlatformUser
from app.schemas.parent_auth import ParentActivateRequest, ParentLoginRequest, ParentTokenResponse

router = APIRouter(prefix="/auth/parent", tags=["parent-auth"])

# The activation code is only 7 digits (10M possibilities) — far weaker
# than the long random token it replaced — so unlike a simple equality
# check, wrong guesses need to run out the code rather than staying valid
# indefinitely. Ask the school for "resend activation" to get a fresh one.
_MAX_INVITE_TOKEN_ATTEMPTS = 5


@router.post("/activate", response_model=ParentTokenResponse)
def activate(payload: ParentActivateRequest, platform_db: Session = Depends(get_platform_db)) -> dict:
    """Consumes the invite code emailed when a school first added this
    guardian (see app/api/routes/guardians.py) and sets their password.
    """
    user = platform_db.query(PlatformUser).filter_by(email=payload.email).first()
    if user is None or not user.invite_token:
        raise HTTPException(status_code=400, detail="Invalid activation code")

    if user.invite_token_expires_at is not None and user.invite_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Activation code has expired — ask the school to re-add you")

    if user.invite_token != payload.invite_token:
        user.invite_token_attempts += 1
        if user.invite_token_attempts >= _MAX_INVITE_TOKEN_ATTEMPTS:
            user.invite_token = None
            user.invite_token_expires_at = None
            user.invite_token_attempts = 0
            platform_db.commit()
            raise HTTPException(
                status_code=400,
                detail="Too many incorrect attempts — ask the school to resend your activation code",
            )
        platform_db.commit()
        raise HTTPException(status_code=400, detail="Invalid activation code")

    user.password_hash = hash_password(payload.password)
    user.email_verified = True
    user.invite_token = None
    user.invite_token_expires_at = None
    user.invite_token_attempts = 0
    platform_db.commit()

    token = create_access_token(subject=str(user.id))
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=ParentTokenResponse)
def login(payload: ParentLoginRequest, platform_db: Session = Depends(get_platform_db)) -> dict:
    user = platform_db.query(PlatformUser).filter_by(email=payload.email).first()
    if user is None or user.password_hash is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(subject=str(user.id))
    return {"access_token": token, "token_type": "bearer"}
