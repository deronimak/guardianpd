import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, get_tenant_db
from app.models.tenant import Student, WelfareAlertLog

router = APIRouter(prefix="/welfare", tags=["welfare"])


@router.get("/alerts/today")
def todays_alerts(
    staff: dict = Depends(get_current_staff),
    tenant_db: Session = Depends(get_tenant_db),
) -> list[dict]:
    """The staff-dashboard side of the welfare job (ARCHITECTURE.md §7) — a
    minimal read view of today's flagged students. No dashboard UI built
    for this yet, just the data.
    """
    today = dt.date.today()
    rows = (
        tenant_db.query(WelfareAlertLog, Student)
        .join(Student, Student.id == WelfareAlertLog.student_id)
        .filter(WelfareAlertLog.alert_date == today)
        .all()
    )
    return [
        {
            "student_id": student.id,
            "student_name": student.name,
            "alert_type": log.alert_type,
            "created_at": log.created_at,
        }
        for log, student in rows
    ]
