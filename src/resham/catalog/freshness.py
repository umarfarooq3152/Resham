"""Grace-period freshness logic: a product missing from a crawl is not
immediately marked out of stock or deleted — only after
`crawl_missing_grace_cycles` consecutive misses, guarding against a
transient partial-page failure. Rows are never hard-deleted."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class FreshnessUpdate:
    missing_streak: int
    in_stock: bool | None  # None means "leave the current in_stock value alone"
    removed_at: datetime | None
    should_clear_removed_at: bool


def on_product_seen() -> FreshnessUpdate:
    """A product was present in this crawl — reset the miss streak and
    un-mark it as removed if it had previously been marked so."""
    return FreshnessUpdate(
        missing_streak=0,
        in_stock=None,  # in_stock is recomputed from the fresh variant data, not touched here
        removed_at=None,
        should_clear_removed_at=True,
    )


def on_product_missing(
    current_missing_streak: int, grace_cycles: int
) -> FreshnessUpdate:
    """A product previously seen for this brand was absent from the latest
    successful crawl. Only mark it out of stock once it has been missing
    for `grace_cycles` consecutive crawls."""
    new_streak = current_missing_streak + 1
    if new_streak >= grace_cycles:
        return FreshnessUpdate(
            missing_streak=new_streak,
            in_stock=False,
            removed_at=datetime.now(timezone.utc),
            should_clear_removed_at=False,
        )
    return FreshnessUpdate(
        missing_streak=new_streak,
        in_stock=None,
        removed_at=None,
        should_clear_removed_at=False,
    )
