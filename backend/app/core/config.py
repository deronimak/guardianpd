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


settings = Settings()
