from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    database_url: str = (
        "postgresql+asyncpg://interviewbuddy:interviewbuddy@localhost:5432/interviewbuddy"
    )
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"

    # R2 / MinIO (S3-compatible)
    r2_access_key_id: str = "minioadmin"
    r2_secret_access_key: str = "minioadmin"
    r2_bucket: str = "interviewbuddy-docs"
    r2_endpoint_url: str = "http://localhost:9000"
    r2_region: str = "auto"

    # Upload / extract caps (PRD §3.1.1)
    max_upload_bytes: int = 5 * 1024 * 1024
    max_paste_chars: int = 100_000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Alembic needs a sync driver; swap asyncpg → psycopg."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
