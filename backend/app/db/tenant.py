"""Tenant (per-school) database access — ARCHITECTURE.md §2/§9.

Each school gets its own physical Postgres database. This module builds
connection strings for a given tenant database name, caches engines so we
don't reconnect per-request, and provisions new tenant databases when a
school is enrolled.
"""

import re
import threading
from collections import OrderedDict
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

TenantBase = declarative_base()

# We generate tenant_db_name ourselves (see app/api/routes/schools.py) — it
# is never taken directly from user input — but CREATE DATABASE can't use a
# bound parameter for an identifier, so we validate defensively anyway
# before ever interpolating it into SQL.
_VALID_DB_NAME = re.compile(r"^[a-z][a-z0-9_]{2,62}$")

# Bounded LRU, not a plain dict — every school touched during the process's
# life used to keep its own connection pool alive forever, which exhausts
# Postgres's max_connections at any real number of schools (see
# Settings.tenant_engine_cache_size). OrderedDict + a lock rather than
# functools.lru_cache since eviction here must also dispose the evicted
# engine's pool, not just drop a reference to it.
_engine_cache: "OrderedDict[str, Engine]" = OrderedDict()
_engine_cache_lock = threading.Lock()


def tenant_url(tenant_db_name: str) -> str:
    """Public so app/jobs/migrate.py can point TENANT_DATABASE_URL at each
    school's database in turn without duplicating this connection-string
    logic.
    """
    return (
        f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{tenant_db_name}"
    )


def get_tenant_engine(tenant_db_name: str) -> Engine:
    evicted: Engine | None = None
    with _engine_cache_lock:
        engine = _engine_cache.get(tenant_db_name)
        if engine is not None:
            _engine_cache.move_to_end(tenant_db_name)
            return engine

        engine = create_engine(
            tenant_url(tenant_db_name),
            pool_pre_ping=True,
            pool_size=settings.tenant_engine_pool_size,
            max_overflow=settings.tenant_engine_max_overflow,
        )
        _engine_cache[tenant_db_name] = engine

        if len(_engine_cache) > settings.tenant_engine_cache_size:
            _, evicted = _engine_cache.popitem(last=False)  # least-recently-used

    if evicted is not None:
        # Disposed outside the lock — closing pooled connections can block
        # briefly, and nothing else needs the cache held up while it does.
        evicted.dispose()

    return engine


def get_tenant_sessionmaker(tenant_db_name: str) -> sessionmaker:
    return sessionmaker(bind=get_tenant_engine(tenant_db_name), autoflush=False, autocommit=False)


def get_tenant_db_session(tenant_db_name: str) -> Generator[Session, None, None]:
    session = get_tenant_sessionmaker(tenant_db_name)()
    try:
        yield session
    finally:
        session.close()


def provision_tenant_database(tenant_db_name: str) -> None:
    """Creates the tenant's database if it doesn't already exist.

    Table creation happens separately (see the enroll-school route, which
    calls TenantBase.metadata.create_all against the new database). For an
    existing tenant whose schema needs to evolve later, use the Alembic
    tenant config (alembic_tenant.ini) with TENANT_DATABASE_URL pointed at
    that school's database instead of create_all.
    """
    if not _VALID_DB_NAME.match(tenant_db_name):
        raise ValueError(f"Invalid tenant database name: {tenant_db_name!r}")

    admin_engine = create_engine(settings.postgres_admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": tenant_db_name},
            ).first()
            if exists is None:
                conn.execute(text(f'CREATE DATABASE "{tenant_db_name}"'))
    finally:
        admin_engine.dispose()
