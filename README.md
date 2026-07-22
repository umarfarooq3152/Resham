# Resham

Resham is the backend, RAG search engine, web frontend, and Chrome extension for a conversational shopping search product over a crawled catalog of Pakistani clothing brands' Shopify stores. Shoppers describe what they want in plain language, and Resham turns that into a filtered, ranked shortlist of real, in-stock products, each linking out to the brand's own store to complete the purchase — it never handles checkout itself.

## Features

- **Persistent, continuously crawled catalog.** A separate worker process crawls every active brand's public Shopify JSON feed on a recurring schedule (`CRAWL_INTERVAL_HOURS`), storing products in Postgres rather than a request-time cache, with per-brand isolation so one broken storefront can't block the others.
- **RAG search over the catalog.** Products are embedded and indexed incrementally into a Chroma vector store, re-embedding only text that actually changed and doing a cheap metadata-only update for pure price/stock flips.
- **LLM-first conversational intent.** Gemini extracts structured shopping intent from natural-language queries, with Groq as an automatic fallback; a fast-path classifier and diff-merge logic handle session refinements ("blue instead", "under 10,000").
- **Search by image.** Users can upload a photo and get matching products back via a single Gemini vision call; a separate incremental vision classifier also tags crawled product images in the background.
- **Exact-first ranking with staged relaxation** across audience, budget, size, color, and occasion, falling back to near-matches only when exact results are sparse.
- **Chrome extension** ("Resham — Find Your Match") that searches the current Shopify store's crawled catalog from the browser, supports voice queries transcribed via Groq, and can add an item straight to that store's own cart.
- **Auth, wishlist, devices, and curated collections** as first-class API resources, plus admin, session, and rate-limited endpoints.
- Request logging middleware, structured error responses, and rate limiting (`slowapi`) on the API.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy (async) + Alembic, PostgreSQL (`asyncpg`), Redis (session/chat cache), Chroma (vector store), APScheduler
- **LLM/AI:** Google Gemini (`google-genai`), Groq
- **Web frontend:** React 19, Vite, TypeScript, Tailwind CSS v4 (in `web/`)
- **Browser extension:** TypeScript, Manifest V3, Playwright (E2E), Vitest (unit tests) (in `extension/`)
- **Auth/security:** JWT (`PyJWT`), `bcrypt`
- **Testing:** pytest, pytest-asyncio, hypothesis (property-based tests), 80% coverage gate
- **Deployment:** Docker / Docker Compose for local dev; Railway (API, worker, Postgres, Redis, Chroma, and the web frontend as five separate services)

## Setup / Installation

### Backend (API + worker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # DATABASE_URL, GEMINI_API_KEY, GROQ_API_KEY, REDIS_URL, CHROMA_HOST/PORT, JWT_SECRET_KEY, ...
alembic upgrade head
```

Or bring up the whole stack (Postgres, Redis, Chroma, migration, API, worker) with:

```bash
docker compose up
```

### Web frontend

```bash
cd web
npm install
```

### Browser extension

```bash
cd extension
npm install
npm run build
```

## Usage

```bash
uvicorn resham.api.main:app --reload      # API at http://localhost:8000
python -m resham.worker.main              # recurring crawl + classify + index cycle
```

```bash
cd web && npm run dev                     # frontend at http://localhost:3000
```

Load the extension by building it (`npm run build` in `extension/`) and loading `extension/dist` as an unpacked extension from `chrome://extensions` with Developer mode enabled; the backend must be running at `http://localhost:8000` with `GROQ_API_KEY` set for voice transcription.

### Testing

```bash
pytest                    # backend: unit, integration, property, and regression tests (80% coverage gate)
```

```bash
cd extension && npm test && npm run test:e2e
```

See `docs/RAILWAY.md` for the full production deployment layout (five Railway services: Postgres, Redis, Chroma, API, worker, and Web).
