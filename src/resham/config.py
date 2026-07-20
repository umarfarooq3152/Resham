"""Application configuration — environment variables with fail-fast validation."""

from functools import lru_cache

from pydantic import field_validator
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
    # Lowered from 4: this bounds how many brands crawl *concurrently*, but
    # concurrency alone doesn't stop a burst — see crawl_stagger_*_seconds,
    # the actual fix for hitting many Cloudflare-protected storefronts
    # within seconds of each other.
    crawl_concurrency: int = 2
    crawl_missing_grace_cycles: int = 2  # consecutive misses before a product is marked OOS
    shopify_products_per_page: int = 250
    shopify_max_pages_per_brand: int = 50
    shopify_request_timeout_seconds: float = 10.0
    # Random delay range before each brand's crawl starts, so ~25 brands
    # spread across ~15-20 minutes instead of firing in one burst (measured:
    # 25 brands with no staggering completed in 39s and got 24/25 rate
    # limited — a request rate that fast across that many different
    # Cloudflare-protected domains reads as bot/scraper traffic to shared
    # IP-reputation heuristics, even though each individual site only saw
    # one request).
    crawl_stagger_min_seconds: float = 20.0
    crawl_stagger_max_seconds: float = 60.0
    # Retry/backoff for a single Shopify page fetch that hit a 429/5xx/
    # timeout — Retry-After is honored when Shopify/Cloudflare sends one;
    # otherwise this is the exponential-backoff base and cap.
    shopify_max_retries: int = 3
    shopify_retry_base_seconds: float = 2.0
    shopify_retry_max_seconds: float = 30.0

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

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_async_database_url(cls, value: str) -> str:
        """Railway's managed Postgres exposes a standard postgres URL while
        SQLAlchemy's async engine requires the asyncpg dialect explicitly."""
        if value.startswith("postgresql+asyncpg://"):
            return value
        if value.startswith("postgres://"):
            return f"postgresql+asyncpg://{value.removeprefix('postgres://')}"
        if value.startswith("postgresql://"):
            return f"postgresql+asyncpg://{value.removeprefix('postgresql://')}"
        return value

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
