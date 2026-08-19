"""Platform (central) DB models — ARCHITECTURE.md §3."""

import uuid
from datetime import datetime
from datetime import time as dt_time

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Time, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.platform import PlatformBase


class School(PlatformBase):
    __tablename__ = "schools"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    tenant_db_name: Mapped[str] = mapped_column(String(63), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="trial")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Welfare-email job config (ARCHITECTURE.md §7). Cutoff times are local
    # wall-clock times in this school's own timezone (IANA identifier, e.g.
    # "America/New_York") — app/jobs/welfare_check.py converts UTC "now"
    # into each school's local time before comparing, so schools in
    # different timezones are handled correctly.
    welfare_email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    drop_off_cutoff_time: Mapped[dt_time] = mapped_column(Time, default=dt_time(9, 30))
    pickup_cutoff_time: Mapped[dt_time] = mapped_column(Time, default=dt_time(18, 0))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")


class Subscription(PlatformBase):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("schools.id"), unique=True)
    plan: Mapped[str] = mapped_column(String(50), default="standard")
    billing_provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # trialing / active / past_due / canceled — see ARCHITECTURE.md §4 for what each gates.
    status: Mapped[str] = mapped_column(String(20), default="trialing")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformUser(PlatformBase):
    """A parent's single login identity, shared across every enrolled school they touch."""

    __tablename__ = "platform_users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Set when a guardian record is first created (ARCHITECTURE.md §8) and
    # cleared once the parent activates their account via /auth/parent/activate.
    invite_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invite_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuardianMembership(PlatformBase):
    """Maps a parent's platform login to their Guardian row inside one school's tenant DB."""

    __tablename__ = "guardian_memberships"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    school_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("schools.id"))
    # No FK — this UUID lives in a different physical database (the school's tenant DB).
    tenant_guardian_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))


class PlatformStaffUser(PlatformBase):
    """Your own ops team (school enrollment, billing support) — distinct from a school's own staff."""

    __tablename__ = "platform_staff_users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="ops")
