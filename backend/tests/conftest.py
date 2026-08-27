"""Shared pytest fixtures for the backend test suite.

Runs against a real local Postgres (the same one docker-compose.yml starts
for dev — see backend/README.md) rather than SQLite: the app relies on
Postgres-specific two-phase commit (app/db/twophase.py) and dynamic
`CREATE DATABASE` per school (app/db/tenant.py), neither of which SQLite
supports. Tests get their own platform database ("platform_test", dropped
and recreated once per test session) so they never touch dev data; each
school a test enrolls gets its own real tenant database, cleaned up by the
`enrolled_school` fixture's teardown.
"""

import os
import uuid

# Must happen before any `app.*` import — app.core.config.Settings() is
# instantiated at import time, and pydantic-settings' env vars take
# precedence over .env, so this redirects the whole app at a disposable
# database before anything else loads.
os.environ["PLATFORM_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/platform_test"
os.environ["POSTGRES_ADMIN_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_USER"] = "postgres"
os.environ["POSTGRES_PASSWORD"] = "postgres"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-32-bytes-long!"
os.environ["QR_SIGNING_KEY"] = "test-only-qr-signing-key"
# Forced blank regardless of the developer's own backend/.env (which has
# real test-mode Paystack/Firebase credentials for manual dev use) — tests
# must be hermetic and exercise the same log-only/501 fallbacks an
# unconfigured install gets (see app/core/email.py, app/core/push.py,
# app/api/routes/billing.py), never a real external API call.
os.environ["PAYSTACK_SECRET_KEY"] = ""
os.environ["FIREBASE_CREDENTIALS_JSON"] = ""
os.environ["SMTP_HOST"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.db.platform import PlatformBase
from app.db.platform import engine as platform_engine
from app.db import tenant as tenant_db_module
from app.core.security import hash_password
from app.main import app
from app.models.platform import PlatformStaffUser

ADMIN_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"


def _admin_connection():
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    return engine


def _terminate_and_drop(db_name: str) -> None:
    admin_engine = _admin_connection()
    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _platform_test_database():
    """Fresh platform_test database for the whole test session."""
    _terminate_and_drop("platform_test")
    admin_engine = _admin_connection()
    try:
        with admin_engine.connect() as conn:
            conn.execute(text('CREATE DATABASE "platform_test"'))
    finally:
        admin_engine.dispose()

    PlatformBase.metadata.create_all(platform_engine)

    yield

    platform_engine.dispose()
    _terminate_and_drop("platform_test")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def drop_tenant_db():
    """Exposes the module-private cleanup helper to tests that enroll a
    school manually instead of via the `enrolled_school` fixture.
    """
    return _terminate_and_drop


@pytest.fixture
def platform_staff(_platform_test_database):
    """A real PlatformStaffUser row — there's no signup endpoint by design
    (see app/jobs/create_platform_staff.py), so tests create one directly.
    """
    from app.db.platform import SessionLocal

    email = f"ops-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-1"
    db = SessionLocal()
    try:
        staff = PlatformStaffUser(name="Test Ops", email=email, password_hash=hash_password(password), role="ops")
        db.add(staff)
        db.commit()
    finally:
        db.close()
    return {"email": email, "password": password}


@pytest.fixture
def platform_auth_headers(client, platform_staff):
    resp = client.post(
        "/auth/platform/login",
        json={"email": platform_staff["email"], "password": platform_staff["password"]},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def enrolled_school(client, platform_auth_headers):
    """Enrolls a fresh school (with its own real tenant database) through
    the actual API, exactly as the Master Admin console would. Tears down
    the tenant database afterward so tests don't leak physical databases.
    """
    slug = f"test-{uuid.uuid4().hex[:10]}"
    admin_password = "admin-temp-pass-1"
    payload = {
        "name": "Test Academy",
        "slug": slug,
        "address": "1 Test Way",
        "phone": "+10000000000",
        "admin_name": "Ada Admin",
        "admin_email": f"admin-{slug}@example.com",
        "admin_temp_password": admin_password,
        "timezone": "UTC",
    }
    resp = client.post("/platform/schools", json=payload, headers=platform_auth_headers)
    assert resp.status_code == 201, resp.text
    school = resp.json()

    yield {
        "school": school,
        "slug": slug,
        "admin_email": payload["admin_email"],
        "admin_password": admin_password,
    }

    tenant_db_name = f"tenant_{slug.replace('-', '_')}"
    engine = tenant_db_module._engine_cache.pop(tenant_db_name, None)
    if engine is not None:
        engine.dispose()
    _terminate_and_drop(tenant_db_name)


@pytest.fixture
def school_admin_headers(client, enrolled_school):
    resp = client.post(
        "/auth/staff/login",
        json={"email": enrolled_school["admin_email"], "password": enrolled_school["admin_password"]},
        headers={"X-School-Slug": enrolled_school["slug"]},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-School-Slug": enrolled_school["slug"]}


@pytest.fixture
def school_staff_headers(client, enrolled_school, school_admin_headers):
    """A role="staff" account (POST /staff, School-Admin-only), logged in —
    for asserting the admin/staff permission split actually holds.
    """
    username = f"staff-{uuid.uuid4().hex[:10]}"
    password = "staff-password-1"
    create_resp = client.post(
        "/staff",
        json={"username": username, "password": password},
        headers=school_admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text

    login = client.post(
        "/auth/staff/login",
        json={"email": username, "password": password},
        headers={"X-School-Slug": enrolled_school["slug"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-School-Slug": enrolled_school["slug"]}
