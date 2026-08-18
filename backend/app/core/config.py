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


settings = Settings()
