"""Wishlist item model.

Unlike Dhaaga (which had no products table and had to reference products by
a loose, unindexed composite-key string), `product_id` here is a real foreign
key into `products.id` — now possible because Resham persists a durable
products table instead of only ever holding products in a request-scoped
live-fetch cache.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from resham.db.base import Base


class WishlistItem(Base):
    """Wishlist entry — device_id + product_id.

    user_id is nullable: anonymous wishlist items (no account) have it
    unset; once a shopper signs up or logs in, items created on that
    device are "claimed" (user_id set) so the wishlist persists across
    devices/browsers instead of being tied to local device storage.
    """

    __tablename__ = "wishlist_items"

    device_id: Mapped[UUID] = mapped_column(
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
