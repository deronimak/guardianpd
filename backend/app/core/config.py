from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    platform_database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/platform"
    postgres_admin_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    qr_signing_key: str = "change-me-dev-only"
    jwt_secret_key: str = "change-me-dev-only"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 720

    # Welfare-email delivery (ARCHITECTURE.md §7). Left blank by default so
    # the welfare job runs end-to-end in local dev without a real provider
    # — see app/core/email.py for the log-only fallback this enables.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "attendance@example.com"
    smtp_use_tls: bool = True

    # Shared-secret gate for /platform/* ops routes (school enrollment,
    # billing). Not a full ops-staff auth system (PlatformStaffUser has no
    # login endpoint yet) — just enough to stop these from being wide open,
    # since they were previously unauthenticated entirely.
    platform_admin_key: str = "change-me-dev-only"

    # Push notifications on scan (ARCHITECTURE.md §5 point 5). Requires a
    # real Firebase project's service-account JSON — left blank by default
    # so the scan flow logs instead of sending, same fallback pattern as
    # SMTP above. See app/core/push.py.
    firebase_credentials_json: str = ""

    # Stripe billing (ARCHITECTURE.md §4). Requires your own Stripe
    # account/API keys — checkout-session creation returns a clear 501
    # until stripe_secret_key is set (there's no meaningful "fake" checkout
    # URL to fall back to the way there is for email/push).
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    stripe_success_url: str = "https://example.com/billing/success"
    stripe_cancel_url: str = "https://example.com/billing/cancel"


settings = Settings()
