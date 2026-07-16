"""Incremental image classification — mirrors vectorstore/indexer.py's
bounded pattern: only products with vision_classified_at IS NULL are
processed, capped per cycle (`vision_classification_batch_size`) so API
cost trickles in over time as the catalog changes rather than a one-time
sweep of the whole catalog. A failed attempt is simply retried on a later
cycle rather than tracked separately — deliberately as simple as the
existing embedding indexer, not a bigger retry system.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.config import get_settings
from resham.db.models.product import Product as ProductRow
from resham.vision.classifier import classify_product_image

logger = logging.getLogger(__name__)


async def classify_incremental(
    session: AsyncSession, *, limit: int | None = None
) -> dict[str, int]:
    """Classify up to `limit` (default: settings.vision_classification_batch_size)
    unclassified, in-stock products by image. Returns counts for observability."""
    settings = get_settings()
    batch_limit = limit if limit is not None else settings.vision_classification_batch_size

    result = await session.execute(
        select(ProductRow)
        .where(
            ProductRow.vision_classified_at.is_(None),
            ProductRow.in_stock.is_(True),
            ProductRow.primary_image_url.is_not(None),
        )
        .order_by(ProductRow.last_seen_at.desc())
        .limit(batch_limit)
    )
    rows = list(result.scalars().all())

    classified = 0
    failed = 0
    for row in rows:
        classification = await classify_product_image(
            row.primary_image_url,
            api_key=settings.gemini_api_key,
            model=settings.gemini_vision_model,
            timeout_seconds=settings.gemini_vision_timeout_seconds,
        )
        if classification is None:
            failed += 1
            continue
        row.vision_category = classification.category
        row.vision_colors = classification.colors
        row.vision_classified_at = datetime.now(timezone.utc)
        if classification.category or classification.colors:
            # Mirrors catalog/repository.py's content-hash-change reset:
            # an already-embedded product's vector was built without these
            # terms, so it must go through embed_new_or_changed again next
            # (index_incremental runs right after this in worker/main.py's
            # cycle) or the new terms would only ever reach Chroma's
            # metadata, never the embedding actually used for ranking.
            row.embedded_at = None
        classified += 1
        # Commit per row (not batched) — a long run killed partway through
        # must not lose already-classified rows back to the start, and each
        # Gemini call already dominates the per-row cost.
        await session.commit()

    if classified or failed:
        logger.info(
            "Vision classification: %d classified, %d failed (retried next cycle)",
            classified, failed,
        )
    return {"classified": classified, "failed": failed}
