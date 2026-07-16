"""Brand registry model."""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from resham.db.base import TimestampedModel


class Brand(TimestampedModel):
    """Brand registry — one per crawled Shopify store."""

    __tablename__ = "brands"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Distinct from is_active: an inactive brand can be kept in the registry
    # (e.g. temporarily paused) without being picked up by the crawler at all.
    crawl_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 'men' | 'women' | 'unisex' — best-effort classification for department
    # based discovery weighting, not a strict gender-exclusivity claim.
    department: Mapped[str] = mapped_column(String(20), default="unisex", nullable=False)
