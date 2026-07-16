"""Product model — durable, crawled catalog record (replaces Dhaaga's live-fetch-only Product)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from resham.db.base import Base


class Product(Base):
    """One row per Shopify product per brand, kept durable across crawls.

    Rows are never hard-deleted — `removed_at` records when a product
    stopped appearing in crawls (see `crawl_missing_grace_cycles` in
    config), preserving `first_seen_at`/`last_seen_at` history.
    """

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("brand_id", "external_id", name="uq_products_brand_external"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    brand_id: Mapped[UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # "{brand_slug}:{external_id}" — same composite-id format Dhaaga used for
    # its live-fetched Product.id, kept for continuity with API consumers
    # (extension, wishlist) and used as the Chroma document id.
    composite_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)

    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Canonical garment family (e.g. "kurta", "shalwar-kameez") computed at
    # ingest via nlp.garments.extract_primary_garment — an exact,
    # low-cardinality column so eligibility SQL can filter on it directly
    # instead of the noisy raw Shopify `category` text.
    product_family: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    shopify_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    department: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    is_kids: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    age_ranges_months: Mapped[list[list[int]]] = mapped_column(JSONB, default=list, nullable=False)
    occasion: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Union across variants — display/reporting only. Real color/size
    # eligibility filtering happens at the variant level (see ProductVariant)
    # so that color+size+price coexist on the same available variant,
    # mirroring Dhaaga's `_matching_variants` semantics.
    colors: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    sizes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    color_images: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)

    min_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)

    primary_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    secondary_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    product_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Hash of ONLY the text fields feeding the Chroma document (title,
    # description_text, category, occasion, colors, tags, shopify_tags) —
    # deliberately excludes price/availability so a price change or stock
    # flip never triggers an expensive re-embed.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Image-derived classification (resham.vision) — a supplementary,
    # non-authoritative signal that fills category/color gaps the text
    # pipeline leaves behind on a sparsely-described product. Deliberately
    # excludes is_kids/age: a photo cannot safely settle that hard
    # constraint, so vision never writes to is_kids/age_ranges_months.
    # NULL vision_classified_at means "not yet classified" (or a prior
    # attempt failed) — resham.vision.service retries it on a later cycle.
    vision_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vision_colors: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    vision_classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # Set once the product has been missing across `crawl_missing_grace_cycles`
    # consecutive successful crawls of its brand. Never hard-deleted.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Consecutive crawl misses since it was last seen — reset to 0 on any hit.
    missing_streak: Mapped[int] = mapped_column(default=0, nullable=False)

    raw_shopify_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan"
    )
