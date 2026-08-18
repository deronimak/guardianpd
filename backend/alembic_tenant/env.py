import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.tenant import TenantBase
from app.models import tenant as tenant_models  # noqa: F401  (registers tables on TenantBase)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# There's no single default tenant database — every school has its own — so
# the target must be passed explicitly:
#   TENANT_DATABASE_URL=postgresql+psycopg2://... alembic -c alembic_tenant.ini upgrade head
tenant_url = os.environ.get("TENANT_DATABASE_URL")
if not tenant_url:
    raise RuntimeError(
        "Set TENANT_DATABASE_URL to the target school's tenant database "
        "before running tenant migrations, e.g.\n"
        '  TENANT_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/tenant_examplehigh" '
        "alembic -c alembic_tenant.ini upgrade head"
    )

config.set_main_option("sqlalchemy.url", tenant_url)
target_metadata = TenantBase.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
