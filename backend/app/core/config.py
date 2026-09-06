from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    platform_database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/platform"
    postgres_admin_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    # Bounds on app/db/tenant.py's tenant-engine LRU cache — without a cap,
    # every school touched during the process's life keeps its own
    # connection pool alive forever, which exhausts Postgres's
    # max_connections long before the database itself is the bottleneck at
    # any real number of schools. Defaults assume Railway's unmodified
    # Postgres image (max_connections=100): cache_size(20) *
    # (pool_size(1) + max_overflow(2)) = 60 tenant connections, worst case,
    # leaving headroom for the platform engine's own pool (~15) plus
    # Alembic/admin connections. Raise these together with your Postgres
    # plan's max_connections, not independently.
    tenant_engine_cache_size: int = 20
    tenant_engine_pool_size: int = 1
    tenant_engine_max_overflow: int = 2

    qr_signing_key: str = "change-me-dev-only"
    jwt_secret_key: str = "change-me-dev-only"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 720

    # Welfare-email delivery (ARCHITECTURE.md §7) via Brevo's HTTP API —
    # not raw SMTP. Railway's outbound network silently times out on SMTP
    # ports (25/465/587), a common PaaS anti-spam egress policy; Brevo's
    # API is plain HTTPS, which is never blocked. Left blank by default so
    # the welfare job runs end-to-end in local dev without a real provider
    # — see app/core/email.py for the log-only fallback this enables.
    brevo_api_key: str = ""
    email_from_address: str = "attendance@example.com"

    # Push notifications on scan (ARCHITECTURE.md §5 point 5). Requires a
    # real Firebase project's service-account JSON — left blank by default
    # so the scan flow logs instead of sending, same fallback pattern as
    # SMTP above. See app/core/push.py.
    firebase_credentials_json: str = ""

    # Paystack billing (ARCHITECTURE.md §4). Requires your own Paystack
    # account/API key — checkout-session creation returns a clear 501 until
    # paystack_secret_key is set (there's no meaningful "fake" checkout URL
    # to fall back to the way there is for email/push). Each checkout is a
    # one-off transaction for a specific Invoice's amount, not a Plan
    # subscription, so there's no plan-code setting. Paystack verifies
    # webhooks with the same secret key (HMAC-SHA512), not a separate
    # webhook secret like Stripe.
    paystack_secret_key: str = ""
    paystack_callback_url: str = "https://example.com/billing/callback"


settings = Settings()
