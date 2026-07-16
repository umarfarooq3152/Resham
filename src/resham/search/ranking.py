"""Hybrid vector + rule-based ranking over an already-eligible candidate set.

Vector similarity only *orders* products that `search/eligibility.py` has
already confirmed satisfy every hard constraint — it never admits a
product eligibility didn't already allow. When the eligible set is bounded
(computed in Postgres), similarity is scored by fetching only those ids'
embeddings from Chroma (`collection.get(ids=...)`) and cosine-ranking in
Python — never `collection.query(where=...)` against the full corpus.

For a fully structured query with no descriptive residue (e.g. "blue kurta
size M under 5000"), the vector step is skipped entirely and ranking is
purely the deterministic rule-based score — matching Dhaaga's existing
behavior, where a fully structured query never needed semantic scoring.
"""

import asyncio
from uuid import UUID

import numpy as np
from chromadb.api.models.Collection import Collection

from resham.catalog.product_view import row_to_pydantic_product
from resham.db.models.product import Product as ProductRow
from resham.nlp.pakistani_events import event_match_score
from resham.services.search_service import (
    _dedupe_color_variants,
    _diversify_by_brand,
    _keyword_score,
    _query_keywords,
)
from resham.vectorstore.embedding import embed_texts


async def _compute_vector_scores(
    rows: list[ProductRow], semantic_query: str, collection: Collection
) -> dict[UUID, float]:
    """Cosine similarity between the query and each row's stored embedding.

    Rows not yet embedded (e.g. indexing hasn't caught up with a very
    recent crawl) are simply absent from the result — callers treat a
    missing score as 0, a safe degradation rather than a failure.
    """
    ids = [row.composite_key for row in rows]
    id_to_uuid = {row.composite_key: row.id for row in rows}

    query_embedding = (await asyncio.to_thread(embed_texts, [semantic_query]))[0]
    query_vec = np.array(query_embedding)
    query_norm = np.linalg.norm(query_vec) or 1.0

    result = await asyncio.to_thread(collection.get, ids=ids, include=["embeddings"])
    got_ids = result.get("ids") or []
    embeddings = result.get("embeddings")
    if embeddings is None:
        return {}

    scores: dict[UUID, float] = {}
    for got_id, embedding in zip(got_ids, embeddings):
        vec = np.array(embedding)
        denom = (np.linalg.norm(vec) * query_norm) or 1.0
        cosine = float(np.dot(vec, query_vec) / denom)
        scores[id_to_uuid[got_id]] = max(0.0, cosine)
    return scores


async def rank_products(
    rows: list[ProductRow],
    *,
    query_text: str = "",
    occasion: str | None = None,
    semantic_query: str = "",
    color: str | None = None,
    collection: Collection | None = None,
) -> list[ProductRow]:
    """Order an already-eligible candidate set by relevance.

    Combines keyword match, occasion fit, and (when there's descriptive
    content and a Chroma collection is supplied) real embedding similarity
    into the same hybrid score shape Dhaaga used, with `semantic_score` now
    a genuine cosine similarity instead of a keyword-overlap approximation.
    """
    if not rows:
        return []

    keywords = _query_keywords(query_text) if query_text else []
    pydantic_by_row_id = {row.id: row_to_pydantic_product(row) for row in rows}

    # Occasion actively filters (matching Dhaaga's `_cached_event_match_score(p,
    # occasion) > 0` gate) rather than only boosting score — it's what makes
    # zero-occasion-match a real outcome for search/relax.py to recover from.
    # It's still "soft" only in the sense that relax.py may retry with
    # occasion=None; within one ranking pass it's an active filter.
    if occasion:
        rows = [row for row in rows if event_match_score(pydantic_by_row_id[row.id], occasion) > 0]
        if not rows:
            return []

    vector_scores: dict[UUID, float] = {}
    if semantic_query.strip() and collection is not None:
        vector_scores = await _compute_vector_scores(rows, semantic_query, collection)

    scored: list[tuple] = []
    for row in rows:
        product = pydantic_by_row_id[row.id]
        keyword_score = _keyword_score(product, keywords)
        occasion_score = event_match_score(product, occasion) if occasion else 0.0
        semantic_score = vector_scores.get(row.id, 0.0)
        hybrid_score = round((keyword_score + occasion_score + 0.75 * semantic_score) * 10) / 10
        scored.append((product, hybrid_score))

    ordered_pydantic = _dedupe_color_variants(_diversify_by_brand(scored), requested_color=color)

    row_by_composite_key = {row.composite_key: row for row in rows}
    return [row_by_composite_key[p.id] for p in ordered_pydantic if p.id in row_by_composite_key]
