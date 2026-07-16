"""Import every model so `Base.metadata` is complete for Alembic autogenerate."""

from resham.db.models.brand import Brand
from resham.db.models.chat import ChatMessage
from resham.db.models.collections import Collection
from resham.db.models.crawl_run import CrawlRun, CrawlRunBrand
from resham.db.models.device import Device
from resham.db.models.events import SessionEvent
from resham.db.models.product import Product
from resham.db.models.product_variant import ProductVariant
from resham.db.models.query_cache import QueryIntentCache
from resham.db.models.user import User
from resham.db.models.wishlist import WishlistItem

__all__ = [
    "Brand",
    "ChatMessage",
    "Collection",
    "CrawlRun",
    "CrawlRunBrand",
    "Device",
    "SessionEvent",
    "Product",
    "ProductVariant",
    "QueryIntentCache",
    "User",
    "WishlistItem",
]
