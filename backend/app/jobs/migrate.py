"""Apply all pending migrations — platform database, then every school's
tenant database in turn.

Run automatically before the app starts (see Dockerfile's CMD) so schema
changes never have to be applied to production by hand. Safe to run on
every deploy: Alembic's upgrade is a no-op once a database is already at
its head revision, same idempotency guarantee the rest of app/jobs/
already relies on (see generate_invoices.py, welfare_check.py).

The platform migration failing is treated as fatal — if that goes wrong
something is fundamentally broken and the app shouldn't start. One
school's tenant database failing to migrate is logged and skipped rather
than blocking every other school from coming up.
"""

import logging
import os

from alembic import command
from alembic.config import Config

from app.db.platform import SessionLocal
from app.db.tenant import tenant_url
from app.models.platform import School

logger = logging.getLogger(__name__)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _alembic_config(ini_name: str) -> Config:
    return Config(os.path.join(_BACKEND_DIR, ini_name))


def migrate_platform() -> None:
    command.upgrade(_alembic_config("alembic_platform.ini"), "head")
    logger.info("platform database migrated to head")


def migrate_all_tenants() -> tuple[int, int]:
    """Returns (succeeded, failed) counts."""
    db = SessionLocal()
    try:
        schools = db.query(School).all()
    finally:
        db.close()

    succeeded = 0
    failed = 0
    for school in schools:
        # alembic_tenant/env.py reads this env var directly (there's no
        # single default tenant database, so it can't be baked into the
        # .ini the way the platform one is).
        os.environ["TENANT_DATABASE_URL"] = tenant_url(school.tenant_db_name)
        try:
            command.upgrade(_alembic_config("alembic_tenant.ini"), "head")
            succeeded += 1
            logger.info("%s: tenant database migrated to head", school.slug)
        except Exception:
            failed += 1
            logger.exception("%s: tenant database migration failed", school.slug)
    return succeeded, failed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_platform()  # fatal on failure — an uncaught exception here stops the container from starting
    ok, failed = migrate_all_tenants()
    print(f"Platform migrated. Tenants: {ok} migrated, {failed} failed.")
    # Intentionally not fatal: one school's tenant DB being unreachable
    # shouldn't take the whole platform down for every other school.
