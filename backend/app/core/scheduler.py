"""In-process periodic runner for the per-child metered billing jobs.

generate_invoices_for_all_schools / mark_overdue_invoices
(app/jobs/generate_invoices.py) were written as plain, idempotent,
externally-triggered CLI scripts (see that module's docstring). Nothing in
this deployment currently schedules them, so the Master Admin console's
Invoices page would otherwise never see new data. A BackgroundScheduler
(thread-based, matching the jobs' own synchronous/blocking style — no
asyncio wrapping needed) is the simplest fix for the current single-worker
Railway deployment; it assumes exactly one uvicorn worker process, since
running this in more than one worker would run each job that many times
concurrently (harmless here thanks to the jobs' own idempotency guards, but
still redundant work worth noting if the deployment ever scales out).
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.jobs.backup_databases import backup_all_databases
from app.jobs.generate_invoices import generate_invoices_for_all_schools, mark_overdue_invoices

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()


def _run_generate_invoices() -> None:
    created = generate_invoices_for_all_schools()
    logger.info("scheduled generate_invoices: created %d invoice(s)", created)


def _run_mark_overdue() -> None:
    marked = mark_overdue_invoices()
    logger.info("scheduled mark_overdue_invoices: marked %d invoice(s) overdue", marked)


def _run_backup_databases() -> None:
    summary = backup_all_databases()
    logger.info("scheduled backup_databases: %s", summary)


def start_scheduler() -> None:
    _scheduler.add_job(_run_generate_invoices, "interval", hours=6, id="generate_invoices", replace_existing=True)
    _scheduler.add_job(_run_mark_overdue, "interval", hours=6, id="mark_overdue_invoices", replace_existing=True)
    # A fixed off-peak UTC hour rather than "interval" — a backup landing
    # at a predictable time each day makes "did last night's backup run?"
    # a sane question to ask when checking up on this.
    _scheduler.add_job(
        _run_backup_databases, CronTrigger(hour=3, minute=0), id="backup_databases", replace_existing=True
    )
    _scheduler.start()
    logger.info("scheduler started: generate_invoices + mark_overdue_invoices every 6h, backup_databases daily 03:00 UTC")


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
