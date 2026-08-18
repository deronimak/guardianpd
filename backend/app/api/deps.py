"""Shared FastAPI dependencies: tenant resolution, subscription gating, staff auth.

Tenant resolution here uses a simple `X-School-Slug` header. That's enough
to demonstrate the platform-DB -> tenant-DB routing (ARCHITECTURE.md §2/§9)
for this scaffold; a hardened version should derive the school from the
authenticated staff/parent session rather than trusting a client-supplied
header for anything beyond initial login.
"""

from collections.abc import Generator

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.platform import get_platform_db
from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import School, Subscription

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/staff/login", auto_error=False)
oauth2_scheme_parent = OAuth2PasswordBearer(tokenUrl="/auth/parent/login", auto_error=False)


def get_school(
    x_school_slug: str = Header(..., alias="X-School-Slug"),
    platform_db: Session = Depends(get_platform_db),
) -> School:
    school = platform_db.query(School).filter_by(slug=x_school_slug).first()
    if school is None:
        raise HTTPException(status_code=404, detail="Unknown school")
    return school


def get_tenant_db(school: School = Depends(get_school)) -> Generator[Session, None, None]:
    session = get_tenant_sessionmaker(school.tenant_db_name)()
    try:
        yield session
    finally:
        session.close()


def require_active_subscription(
    school: School = Depends(get_school),
    platform_db: Session = Depends(get_platform_db),
) -> School:
    """ARCHITECTURE.md §4: lapsed subscription blocks QR issuance AND scanning."""
    subscription = platform_db.query(Subscription).filter_by(school_id=school.id).first()
    if subscription is None or subscription.status not in ("trialing", "active"):
        raise HTTPException(
            status_code=402,
            detail="This school's subscription is inactive. QR scanning and issuance are disabled until it's resolved.",
        )
    return school


def get_current_staff(
    token: str | None = Depends(oauth2_scheme),
    school: School = Depends(get_school),
) -> dict:
    if token is None:
        raise HTTPException(status_code=401, detail="Missing credentials")
    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if claims.get("school_id") != str(school.id):
        raise HTTPException(status_code=403, detail="Token is not valid for this school")
    return claims


def get_current_parent(token: str | None = Depends(oauth2_scheme_parent)) -> dict:
    """Parent auth is platform-level, not school-scoped — a parent's login
    identity spans every school their children attend (ARCHITECTURE.md §8),
    unlike staff whose token is pinned to one school above.
    """
    if token is None:
        raise HTTPException(status_code=401, detail="Missing credentials")
    try:
        return decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_platform_admin(x_platform_admin_key: str = Header(..., alias="X-Platform-Admin-Key")) -> None:
    """Gates the platform-ops surface (school enrollment, billing). Not a
    full auth system — PlatformStaffUser has no login endpoint yet — just a
    shared secret so these routes aren't wide open to anyone who finds the
    API.
    """
    if x_platform_admin_key != settings.platform_admin_key:
        raise HTTPException(status_code=401, detail="Invalid platform admin key")
