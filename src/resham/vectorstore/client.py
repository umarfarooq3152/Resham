"""Chroma client/collection wiring.

The crawler/indexer (worker process) and the API process both connect to a
Chroma **server** (`chroma run` / the `chroma` service in docker-compose)
via HttpClient, rather than sharing a file-backed PersistentClient — a
persistent client is not safe for concurrent multi-process access, and one
process here writes (the worker) while the other only reads (the API).
"""

from functools import lru_cache

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

from resham.config import get_settings
from resham.vectorstore.embedding import get_embedding_function


@lru_cache
def get_chroma_client() -> ClientAPI:
    settings = get_settings()
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def get_collection(client: ClientAPI | None = None) -> Collection:
    settings = get_settings()
    client = client or get_chroma_client()
    return client.get_or_create_collection(
        name=settings.chroma_collection_name,
        embedding_function=get_embedding_function(),
        metadata={"embedding_model_version": settings.embedding_model_version},
    )
