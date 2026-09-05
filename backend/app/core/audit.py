"""Guardian/student change history — Master Admin's per-school Activity log.

Purely additive: every mutation still does its own commit exactly as
before (app/api/routes/guardians.py, students.py, schools.py); this just
adds one more row to the same transaction, no new commit boundary.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.tenant import AuditLogEntry


def record_audit(
    tenant_db: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    summary: str,
    actor_label: str,
) -> None:
    tenant_db.add(
        AuditLogEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            summary=summary,
            actor_label=actor_label,
        )
    )


def resolve_staff_actor_label(tenant_db: Session, claims: dict) -> str:
    """For school-scoped endpoints (guardians.py, students.py) — claims come
    from app.api.deps.get_current_staff, whose "sub" is a StaffUser id.
    """
    from app.models.tenant import StaffUser

    staff_id = claims.get("sub")
    staff = tenant_db.get(StaffUser, uuid.UUID(staff_id)) if staff_id else None
    return f"Staff: {staff.name}" if staff is not None else "Staff: unknown"


def resolve_platform_actor_label(platform_db: Session, claims: dict) -> str:
    """For Master-Admin endpoints (schools.py) — claims come from
    app.api.deps.require_platform_staff, whose "sub" is a PlatformStaffUser id.
    """
    from app.models.platform import PlatformStaffUser

    staff_id = claims.get("sub")
    staff = platform_db.get(PlatformStaffUser, uuid.UUID(staff_id)) if staff_id else None
    return f"Platform: {staff.name}" if staff is not None else "Platform: unknown"
