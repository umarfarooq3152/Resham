"""Application configuration — environment variables with fail-fast validation."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Database (structured source of truth — Postgres)
    database_url: str
    database_echo: bool = False

    # LLM Providers
    gemini_api_key: str
    groq_api_key: str
    gemini_model: str = "gemini-3.1-flash-lite"
    groq_model: str = "llama-3.1-8b-instant"
    gemini_timeout_seconds: float = 4.0
    groq_timeout_seconds: float = 6.0
    gemini_rate_limit_cooldown_seconds: float = 300.0
    llm_first_intent_enabled: bool = True

    # Image classification (resham.vision) — reuses the Gemini key above.
    # Runs incrementally, capped per worker cycle, so cost trickles in over
    # time rather than a one-time sweep of the whole catalog.
    gemini_vision_model: str = "gemini-3.1-flash-lite"
    gemini_vision_timeout_seconds: float = 8.0
    vision_classification_batch_size: int = 50

    # Browser extension — all crawled brands are supported (not a single-store MVP)
    extension_allowed_origins: str = ""
    extension_request_timeout_seconds: float = 25.0
    extension_rank_candidate_limit: int = 40
    extension_result_limit: int = 40

    # Session cache (Redis holds only ephemeral chat/session state — no product cache)
    redis_url: str
    session_store_backend: str = "redis"  # "memory" or "redis"
    session_ttl_hours: int = 6
    query_cache_ttl_hours: int = 24

    # Vector store (Chroma, client/server mode)
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection_name: str = "products_v1"
    embedding_model_version: str = "onnx-mini-lm-l6-v2"

    # Crawler / worker
    crawl_interval_hours: float = 4.0
    crawl_concurrency: int = 4
    crawl_missing_grace_cycles: int = 2  # consecutive misses before a product is marked OOS
    shopify_products_per_page: int = 250
    shopify_max_pages_per_brand: int = 50
    shopify_request_timeout_seconds: float = 10.0

    # CORS
    frontend_origin: str = "http://localhost:3000"

    # Auth
    jwt_secret_key: str
    jwt_expiry_days: int = 30

    # Environment
    environment: str = "development"
    debug: bool = False
    log_level: str = "info"

    # Rate limiting
    rate_limit_session_message_per_min: int = 20
    rate_limit_general_per_min: int = 60
    rate_limit_auth_per_min: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

    def validate_required_secrets(self) -> None:
        """Fail fast if critical secrets are missing."""
        required = [
            "database_url",
            "gemini_api_key",
            "groq_api_key",
            "redis_url",
            "jwt_secret_key",
        ]
        missing = [key for key in required if not getattr(self, key)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()  # type: ignore
    settings.validate_required_secrets()
    return settings
