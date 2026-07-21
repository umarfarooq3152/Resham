FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 resham
WORKDIR /app

# Dependencies are installed against a stub package first, keyed only on
# pyproject.toml, so an edit to src/ later doesn't invalidate this layer
# and force every dependency to be re-downloaded on each rebuild.
COPY pyproject.toml ./
# --timeout/--retries survive a slow or flaky registry connection instead of
# aborting a large dependency (onnxruntime, grpcio) mid-download.
RUN mkdir -p src/resham && touch src/resham/__init__.py \
    && pip install --no-cache-dir --timeout 180 --retries 8 . \
    && rm -rf src

COPY src ./src
RUN pip install --no-cache-dir --no-deps --force-reinstall .

COPY alembic.ini ./
COPY migrations ./migrations

# Pre-created and owned by resham so that when docker-compose.yml mounts a
# fresh named volume here, Docker copies this directory's ownership into
# the volume on first mount — otherwise the volume's mount point defaults
# to root:root and the embedding model download (as the non-root resham
# user below) fails with a plain PermissionError.
RUN mkdir -p /home/resham/.cache/chroma && chown -R resham:resham /home/resham/.cache

USER resham

# Overridden per-service in docker-compose.yml (api / worker / migrate).
CMD ["uvicorn", "resham.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
