"""Covers app/db/tenant.py's bounded LRU engine cache. Before this, every
school touched during the process's life kept its own connection pool
alive forever (a plain dict, never evicted) — harmless at a handful of
schools, but it exhausts Postgres's max_connections long before the
database itself becomes the bottleneck at any real number of schools.

Uses fake tenant db names rather than real ones — create_engine() never
opens a connection eagerly, so this can exercise cache/eviction behavior
without a real Postgres database per entry.
"""

import pytest

import app.db.tenant as tenant_db


@pytest.fixture(autouse=True)
def _clean_engine_cache():
    tenant_db._engine_cache.clear()
    yield
    for engine in tenant_db._engine_cache.values():
        engine.dispose()
    tenant_db._engine_cache.clear()


def test_evicts_least_recently_used_once_over_capacity(monkeypatch):
    monkeypatch.setattr(tenant_db.settings, "tenant_engine_cache_size", 2)

    disposed = []
    original_dispose = tenant_db.Engine.dispose
    monkeypatch.setattr(
        tenant_db.Engine, "dispose", lambda self: (disposed.append(self), original_dispose(self))[1]
    )

    engine_a = tenant_db.get_tenant_engine("tenant_cache_test_a")
    tenant_db.get_tenant_engine("tenant_cache_test_b")
    assert list(tenant_db._engine_cache.keys()) == ["tenant_cache_test_a", "tenant_cache_test_b"]

    tenant_db.get_tenant_engine("tenant_cache_test_c")

    assert list(tenant_db._engine_cache.keys()) == ["tenant_cache_test_b", "tenant_cache_test_c"]
    assert engine_a in disposed


def test_reaccessing_an_entry_marks_it_recently_used(monkeypatch):
    monkeypatch.setattr(tenant_db.settings, "tenant_engine_cache_size", 2)

    tenant_db.get_tenant_engine("tenant_cache_test_a")
    tenant_db.get_tenant_engine("tenant_cache_test_b")
    tenant_db.get_tenant_engine("tenant_cache_test_a")  # touch A again — B is now the LRU entry

    tenant_db.get_tenant_engine("tenant_cache_test_c")

    assert list(tenant_db._engine_cache.keys()) == ["tenant_cache_test_a", "tenant_cache_test_c"]


def test_returns_the_same_engine_instance_on_cache_hit():
    first = tenant_db.get_tenant_engine("tenant_cache_test_reuse")
    second = tenant_db.get_tenant_engine("tenant_cache_test_reuse")
    assert first is second
