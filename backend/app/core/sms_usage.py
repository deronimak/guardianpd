"""SMS usage metering for billing.

Every SMS alert the provider accepts is recorded in the school's own database
as a Notification row with channel "sms" (see app/api/routes/attendance.py),
so a school's usage in a billing period is a count of those rows. Only
messages actually accepted by the provider are recorded (see
app/core/sms.py: send_sms returns True only when a message was really sent),
so skipped, duplicate and dev-mode sends are never billed.
"""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func

from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import School
from app.models.tenant import Notification


def count_sms(school: School, period_start: dt.date, period_end: dt.date) -> int:
    """SMS sent from period_start (inclusive) up to period_end (exclusive), UTC days."""
    start = dt.datetime.combine(period_start, dt.time.min, tzinfo=dt.timezone.utc)
    end = dt.datetime.combine(period_end, dt.time.min, tzinfo=dt.timezone.utc)
    tenant_db = get_tenant_sessionmaker(school.tenant_db_name)()
    try:
        return (
            tenant_db.query(func.count(Notification.id))
            .filter(Notification.channel == "sms", Notification.sent_at >= start, Notification.sent_at < end)
            .scalar()
            or 0
        )
    finally:
        tenant_db.close()


def sms_charge(count: int, rate_naira) -> int:
    """Whole-naira charge for `count` messages at `rate_naira` each (the rate may
    have kurus-style fractions, e.g. 6.50); rounded half-up."""
    amount = Decimal(count) * Decimal(str(rate_naira or 0))
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
