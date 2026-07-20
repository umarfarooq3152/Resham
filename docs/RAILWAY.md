# Railway deployment

This project is deployed as five Railway services. Railway does not run the
local `docker-compose.yml` directly; each container becomes its own service.

| Railway service | Source | Purpose |
| --- | --- | --- |
| `Postgres` | Railway managed PostgreSQL | Durable catalog |
| `Redis` | Railway managed Redis | Chat/session cache |
| `chroma` | Docker image `chromadb/chroma:0.5.23` | Vector index |
| `API` | Repository root, `railway.toml` | Public FastAPI backend |
| `worker` | Repository root, `railway.worker.toml` | Crawls, image classification, indexing |
| `Web` | Repository root with root directory `web` | Public Vite frontend |

## 1. Provision data services

Create a Railway project, then add managed **PostgreSQL** and **Redis**
services. Add a Docker Image service named `chroma` using
`chromadb/chroma:0.5.23`; attach a Railway volume at `/chroma/chroma`.
Do not expose Postgres, Redis, or Chroma publicly.

## 2. Deploy the API

Create an `API` service from this repository's root. Railway detects
`railway.toml`, runs the Alembic migration before the API starts, and checks
`/healthz` before routing traffic. Generate a public domain for this service.

Set these API variables (Railway reference syntax assumes the service names in
the table above):

```dotenv
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
CHROMA_HOST=chroma.railway.internal
CHROMA_PORT=8000
CHROMA_COLLECTION_NAME=products_v1
GEMINI_API_KEY=<Gemini key>
GROQ_API_KEY=<Groq key>
JWT_SECRET_KEY=<random 32+ byte secret>
ENVIRONMENT=production
LOG_LEVEL=info
SESSION_STORE_BACKEND=redis
FRONTEND_ORIGIN=https://${{Web.RAILWAY_PUBLIC_DOMAIN}}
```

The app normalizes Railway's normal `postgresql://` URL to SQLAlchemy's
required `postgresql+asyncpg://` form at startup, so the Postgres reference is
safe to use unchanged.

## 3. Deploy the worker

Create a second service from the same repository root. In its Settings, set
the Config-as-Code path to `/railway.worker.toml`. Give it the same data and
provider variables as `API` (`DATABASE_URL`, `REDIS_URL`, `CHROMA_HOST`,
`CHROMA_PORT`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `JWT_SECRET_KEY`, and the
crawler settings from `.env.example`). It stays private and has no domain.

The API owns migrations; do not add a second migration command to the worker.

## 4. Deploy the web app

Create a `Web` service from the same repository. Set its root directory to
`web`, generate a public domain, and set this build-time variable before
deploying:

```dotenv
VITE_API_BASE_URL=https://${{API.RAILWAY_PUBLIC_DOMAIN}}
```

The web Dockerfile builds the Vite bundle and serves the SPA through Caddy.
After the Web domain exists, deploy the API once more so its
`FRONTEND_ORIGIN` reference is resolved for CORS.

## Verify

Open `https://<API domain>/healthz`; it should report `status: "ok"` and all
three dependencies as `ok`. Then open the Web domain and upload a JPEG, PNG,
or WebP through the image button. The request should reach
`POST /products/visual-search`.
