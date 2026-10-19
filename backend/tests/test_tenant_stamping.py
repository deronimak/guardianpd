"""New schools must carry a migration history, and unstamped ones that match the
models are repaired by the deploy-time migration job instead of failing."""

from sqlalchemy import create_engine, text

from app.db.tenant import tenant_url
from app.jobs.migrate import _stamp_if_unstamped_and_current


def _tenant_name(enrolled_school):
    return f"tenant_{enrolled_school['slug'].replace('-', '_')}"


def _version(enrolled_school):
    engine = create_engine(tenant_url(_tenant_name(enrolled_school)))
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("select version_num from alembic_version")).all()
        return rows[0][0] if rows else None
    except Exception:
        return None
    finally:
        engine.dispose()


def test_newly_enrolled_school_is_stamped_at_head(enrolled_school):
    from alembic.script import ScriptDirectory

    from app.jobs.migrate import _alembic_config

    head = ScriptDirectory.from_config(_alembic_config("alembic_tenant.ini")).get_current_head()
    assert _version(enrolled_school) == head


def test_unstamped_but_current_database_is_stamped_by_the_migration_job(enrolled_school):
    url = tenant_url(_tenant_name(enrolled_school))
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("drop table alembic_version"))
    engine.dispose()
    assert _version(enrolled_school) is None

    assert _stamp_if_unstamped_and_current(url) is True
    assert _version(enrolled_school) is not None
    # Already stamped: nothing to do.
    assert _stamp_if_unstamped_and_current(url) is False


def test_unstamped_database_that_differs_from_the_models_is_left_alone(enrolled_school):
    url = tenant_url(_tenant_name(enrolled_school))
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("drop table alembic_version"))
        conn.execute(text("alter table students drop column photo"))
    engine.dispose()

    assert _stamp_if_unstamped_and_current(url) is False
    assert _version(enrolled_school) is None
