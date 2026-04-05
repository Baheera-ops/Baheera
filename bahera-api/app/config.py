"""
Application configuration loaded from environment variables.
Uses Pydantic Settings for validation and type coercion.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Application ──────────────────────────────────────────────────
    APP_NAME: str = "Bahera API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # ── Database (Supabase PostgreSQL) ───────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/bahera"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ── Supabase ─────────────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # ── OpenAI ───────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ── Meta / WhatsApp ──────────────────────────────────────────────
    META_APP_SECRET: str = ""
    META_VERIFY_TOKEN: str = "bahera_verify_2026"
    WHATSAPP_PHONE_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""

    # ── Security ─────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    API_RATE_LIMIT: int = 100  # requests per minute per org

    # ── Feature Flags ────────────────────────────────────────────────
    ENABLE_AI_SCORING: bool = True
    ENABLE_FOLLOW_UPS: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
