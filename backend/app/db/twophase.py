"""Cross-database atomicity for platform-DB + tenant-DB writes.

Some operations (enrolling a school, creating a guardian) need to write to
both the platform DB and one school's tenant DB together. Since these are
two separate physical databases, a single ordinary transaction can't span
them — writing to each with its own session and two independent commits
(the original approach here) has no atomicity: a crash between the two
commits can leave a PlatformUser with no matching tenant Guardian, or a
School row with no tenant StaffUser.

Fix: SQLAlchemy's two-phase commit support (`Session(twophase=True)`),
which drives PostgreSQL's `PREPARE TRANSACTION` / `COMMIT PREPARED` under
the hood. A single Session is bound to both the platform engine and one
tenant engine; `session.commit()` prepares both transactions and only
commits either if both prepares succeed.

Requires `max_prepared_transactions > 0` on the Postgres server (0 —
disabled — is the default; see docker-compose.yml). Without it, commit()
raises a clear error naming exactly this, rather than silently falling
back to non-atomic behavior.
"""

from sqlalchemy.orm import Session, sessionmaker

from app.db.platform import PlatformBase
from app.db.platform import engine as platform_engine
from app.db.tenant import TenantBase, get_tenant_engine


def get_twophase_session(tenant_db_name: str) -> Session:
    """A Session spanning the platform DB and one tenant DB. Objects mapped
    under PlatformBase route to the platform DB; objects mapped under
    TenantBase route to the given tenant DB. Caller owns the session
    (commit/rollback + close it).
    """
    factory = sessionmaker(
        binds={PlatformBase: platform_engine, TenantBase: get_tenant_engine(tenant_db_name)},
        twophase=True,
        expire_on_commit=False,  # objects stay usable after commit even once the session is closed
    )
    return factory()
