"""Product variant model — preserves color+size+price coexistence fidelity."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from resham.db.base import Base


class ProductVariant(Base):
    """One row per Shopify variant. A product is only eligible for a
    color+size+price-constrained query if at least one available variant
    simultaneously satisfies all three — the same coexistence rule as
    Dhaaga's `_matching_variants`, which a product-level-only schema
    cannot express.
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "external_variant_id", name="uq_variants_product_external"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_variant_id: Mapped[str] = mapped_column(String(100), nullable=False)

    color: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # e.g. a third "fabric" option some brands expose alongside color/size.
    extra_options: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    compare_at_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    product: Mapped["Product"] = relationship("Product", back_populates="variants")
