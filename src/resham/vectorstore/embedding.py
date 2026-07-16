"""Embedding function wiring.

Uses Chroma's bundled default embedding function (all-MiniLM-L6-v2 via
onnxruntime, no torch dependency) so indexing and query-time embedding are
fully offline once the ~80MB model is cached, and — critically — always use
the exact same model/version, since mismatched embedding models make cosine
similarity scores meaningless.
"""

from functools import lru_cache

from chromadb.api.types import EmbeddingFunction
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


@lru_cache
def get_embedding_function() -> EmbeddingFunction:
    return DefaultEmbeddingFunction()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with the shared embedding function.

    Callers on an asyncio event loop should run this via a thread/process
    pool (e.g. `asyncio.to_thread`) — embedding is CPU-bound and must not
    block the loop.
    """
    if not texts:
        return []
    return list(get_embedding_function()(texts))
