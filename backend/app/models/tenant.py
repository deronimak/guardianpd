"""Tenant (per-school) DB models — ARCHITECTURE.md §3.

Everything here lives inside one school's own database. There is no
school_id column anywhere in this file: the database itself is the tenant
boundary (ARCHITECTURE.md §2).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.tenant import TenantBase


class StaffUser(TenantBase):
    __tablename__ = "staff_users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")  # admin / teacher / front_desk


class Guardian(TenantBase):
    __tablename__ = "guardians"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # No FK — points back to PlatformUser.id in the platform DB.
    platform_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Student(TenantBase):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class GuardianStudentLink(TenantBase):
    """Many-to-many: which guardians may pick up/drop off which children."""

    __tablename__ = "guardian_student_links"
    __table_args__ = (UniqueConstraint("guardian_id", "student_id", name="uq_guardian_student"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guardian_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("guardians.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("students.id"))
    relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_authorized_pickup: Mapped[bool] = mapped_column(Boolean, default=True)


class QRCredential(TenantBase):
    """The signed, static, printed QR token for one guardian at this school."""

    __tablename__ = "qr_credentials"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guardian_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("guardians.id"))
    token: Mapped[str] = mapped_column(String(500), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttendanceEvent(TenantBase):
    __tablename__ = "attendance_events"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("students.id"))
    guardian_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("guardians.id"))
    type: Mapped[str] = mapped_column(String(20))  # drop_off / pick_up
    scanned_by_staff_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ExpectedAbsence(TenantBase):
    """A planned absence — required input to the welfare-email job so it doesn't false-alarm."""

    __tablename__ = "expected_absences"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("students.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SchoolCalendar(TenantBase):
    __tablename__ = "school_calendar"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_school_day: Mapped[bool] = mapped_column(Boolean, default=True)


class Notification(TenantBase):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guardian_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("guardians.id"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("attendance_events.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(20))  # push / email
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
