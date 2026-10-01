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

    # Embeddings (local FastEmbed)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dims: int = 384

    # OpenRouter — single model for grill, claims, score, and report
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    default_grill_model: str = "qwen/qwen3.7-flash"
    # auto | heuristic | openrouter
    claims_backend: str = "auto"
    # auto | stub | openrouter — auto uses OpenRouter when key + default model set
    grill_backend: str = "auto"
    # auto | heuristic | openrouter — rubric scorer; heuristic fallback on LLM failure
    score_backend: str = "auto"

    # LiveKit (Cloud or self-hosted `livekit-server --dev`)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "interviewbuddy-grill"
    livekit_token_ttl_seconds: int = 600

    # Sarvam speech. `saaras:v3-realtime` selects the realtime STT (sends lexicon keyterms).
    sarvam_api_key: str = ""
    sarvam_stt_model: str = "saaras:v4"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker: str = ""
    sarvam_language: str = "en-IN"

    @property
    def voice_enabled(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    @property
    def grill_model(self) -> str:
        return self.default_grill_model.strip()

    @property
    def score_model(self) -> str:
        return self.default_grill_model.strip()

    @property
    def report_model(self) -> str:
        return self.default_grill_model.strip()

    @property
    def claims_model(self) -> str:
        return self.default_grill_model.strip()

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
