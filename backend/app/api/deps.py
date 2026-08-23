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

from app.core.security import decode_access_token
from app.db.platform import get_platform_db
from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import School, Subscription

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/staff/login", auto_error=False)
oauth2_scheme_parent = OAuth2PasswordBearer(tokenUrl="/auth/parent/login", auto_error=False)
oauth2_scheme_platform = OAuth2PasswordBearer(tokenUrl="/auth/platform/login", auto_error=False)


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
    """ARCHITECTURE.md §4: a suspended subscription blocks QR issuance AND
    scanning. Suspension is a manual Master Admin action (Manage
    Subscription page) — see app/api/routes/billing.py.
    """
    subscription = platform_db.query(Subscription).filter_by(school_id=school.id).first()
    if subscription is None or subscription.status != "active":
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


def require_school_admin(claims: dict = Depends(get_current_staff)) -> dict:
    """Gates the School-Admin-only mobile surface (staff-account creation,
    guardian enrollment/search/resend-activation) — the GuardianPD rework
    splits StaffUser.role into "admin" vs "staff"; School Staff accounts
    (role="staff") get 403'd here rather than silently sharing admin powers.
    """
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="School admin access required")
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


def require_platform_staff(token: str | None = Depends(oauth2_scheme_platform)) -> dict:
    """Gates the platform-ops surface (school enrollment, billing) with a
    real PlatformStaffUser login — replaces the old shared
    X-Platform-Admin-Key. Bootstrap the first account with
    `python -m app.jobs.create_platform_staff` (no self-service signup for
    ops accounts, deliberately — see that script's docstring).
    """
    if token is None:
        raise HTTPException(status_code=401, detail="Missing credentials")
    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if claims.get("scope") != "platform_ops":
        raise HTTPException(status_code=403, detail="Not a platform staff token")
    return claims
