"""Incremental Chroma indexing.

Two passes, both bounded to changed rows only:

1. `embed_new_or_changed` — products with `embedded_at IS NULL` (new, or
   text changed since `catalog.repository` reset it on a content-hash
   change) get a full re-embed + upsert of document/metadata/embedding.
2. `sync_metadata_only` — products whose row was touched by a crawl since
   they were last indexed (`updated_at > embedded_at`) but whose text
   didn't change (a pure price/stock flip) get a cheap metadata-only
   `collection.update()` — no re-embedding at all.

Embedding is CPU-bound, so it always runs via `asyncio.to_thread` to avoid
blocking the event loop it's called from.
"""

import asyncio
import logging
from datetime import datetime, timezone

from chromadb.api.models.Collection import Collection
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resham.config import get_settings
from resham.db.models.product import Product as ProductRow
from resham.vectorstore.documents import build_document

logger = logging.getLogger(__name__)


async def embed_new_or_changed(session: AsyncSession, collection: Collection, batch_size: int = 128) -> int:
    """Embed and upsert all in-stock products awaiting indexing.

    Returns the number of products embedded.
    """
    settings = get_settings()
    result = await session.execute(
        select(ProductRow).where(ProductRow.embedded_at.is_(None), ProductRow.in_stock.is_(True))
    )
    rows = list(result.scalars().all())
    total = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        for row in batch:
            document_text, metadata = build_document(row)
            ids.append(row.composite_key)
            documents.append(document_text)
            metadatas.append(metadata)

        await asyncio.to_thread(collection.upsert, ids=ids, documents=documents, metadatas=metadatas)

        now = datetime.now(timezone.utc)
        for row in batch:
            row.embedded_at = now
            # `updated_at` has an `onupdate` default that would otherwise
            # fire on this very write and land microseconds after
            # `embedded_at`, making `updated_at > embedded_at` spuriously
            # true forever and forcing every product through
            # sync_metadata_only on every subsequent run. Pin it explicitly
            # so the two timestamps agree.
            row.updated_at = now
            row.embedding_model_version = settings.embedding_model_version
        # Commit per batch (not just flush) so progress is durable and
        # visible to other connections incrementally — a long run killed
        # partway through must not lose everything back to the start.
        await session.commit()
        total += len(batch)
        logger.info("Embedded %d/%d products", total, len(rows))

    return total


async def sync_metadata_only(session: AsyncSession, collection: Collection, batch_size: int = 256) -> int:
    """Push metadata-only updates (e.g. a stock/price flip) for products
    whose text hasn't changed, avoiding a wasted re-embed."""
    settings = get_settings()
    result = await session.execute(
        select(ProductRow).where(
            ProductRow.embedded_at.is_not(None),
            ProductRow.updated_at > ProductRow.embedded_at,
        )
    )
    rows = list(result.scalars().all())
    total = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        ids: list[str] = []
        metadatas: list[dict] = []
        for row in batch:
            _, metadata = build_document(row)
            ids.append(row.composite_key)
            metadatas.append(metadata)

        await asyncio.to_thread(collection.update, ids=ids, metadatas=metadatas)

        now = datetime.now(timezone.utc)
        for row in batch:
            row.embedded_at = now
            row.updated_at = now  # see embed_new_or_changed for why this is pinned explicitly
            row.embedding_model_version = settings.embedding_model_version
        await session.commit()
        total += len(batch)

    if total:
        logger.info("Synced metadata for %d products", total)
    return total


async def index_incremental(session: AsyncSession, collection: Collection) -> dict[str, int]:
    """Run both indexing passes; returns counts for observability."""
    embedded = await embed_new_or_changed(session, collection)
    synced = await sync_metadata_only(session, collection)
    return {"embedded": embedded, "metadata_synced": synced}
