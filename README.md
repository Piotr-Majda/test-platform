# Test Platform

Portfolio platform for orchestrating UI/API test scenarios with run history, flakiness insights, artifact retention, and optional AI failure analysis.

- Product decisions & slice status: [project-summary.md](project-summary.md)
- Original vision: [prd.md](prd.md)

## Layout

| Path | Role |
|------|------|
| `packages/contracts` | Versioned Pydantic contracts + Redis stream helpers (`test-platform-contracts`) |
| `services/api` | FastAPI + SQLAlchemy orchestration API (SQLite default) |
| `services/executor` | Pluggable executor: `@step` framework, N-worker pool, example tests |
| `apps/web` | React + Vite UI (catalog, scenario config, runs, history, logs, AI reports) |

## Prerequisites

- Python 3.12+ and [uv](https://github.com/astral-sh/uv)
- Node 20+
- Redis on `localhost:6379`  
  Example: `docker run -d --name test-platform-redis -p 6379:6379 redis:7-alpine`

Postgres is the app database (default `public` schema, Alembic-managed).  
Unit tests use in-memory SQLite (`sqlite:///:memory:`). Redis is required for run orchestration.

## Install

```bash
cd packages/contracts && uv sync
cd ../../services/api && uv sync
cd ../executor && uv sync
cd ../../apps/web && npm install
```

## Database migrations (Alembic)

From `services/api`:

```bash
# Apply migrations (requires Postgres + DATABASE_URL)
uv run alembic upgrade head

# Create a new revision after model changes
uv run alembic revision --autogenerate -m "describe change"
```

Default schema: Postgres `public` (no custom schema namespace).

## Run locally (three terminals)

```bash
# 0) Postgres + Redis (or use docker compose for infra only)
docker compose up -d postgres redis

# 1) API (default port 8001)
cd services/api
$env:DATABASE_URL="postgresql+psycopg://platform:platform@localhost:5432/platform"
uv run alembic upgrade head
uv run test-platform-api
```

Or keep using Docker for the full stack (recommended for demos).

```bash
# 2) Executor (registers plugin catalog, starts worker pool)
cd services/executor
uv run test-platform-executor

# 3) UI
cd apps/web
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` to the API (override with `VITE_API_URL` if needed).  
API docs: http://localhost:8001/docs

## Docker Compose (demo)

One stack: Postgres + Redis + API + executor + web.

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| UI | http://localhost:8080 |
| API docs | http://localhost:8001/docs |
| Postgres | `localhost:5432` (user/db/password: `platform`) |

API container runs `alembic upgrade head` on start. Data lives in Docker volumes (`platform-pg`, `platform-data`).

Optional AI key:

```bash
# PowerShell
$env:OPENAI_API_KEY="sk-..."
docker compose up --build
```

Stop containers (keeps volumes):

```bash
docker compose down
```

Wipe demo data too: `docker compose down -v`.

### Quick demo flow

1. Confirm catalog tests under **Available tests** (`google_title`, `flaky_coin`, JustJoinIT, YouTube, …).
2. Click **New scenario** → set SUT, history retention, artifact retention, add/reorder tests → **Save**.
3. **Run** the scenario; inspect **Run status** (steps, errors, artifacts, in-app logs).
4. Open **History** for flakiness, reliability, duration trends, and fingerprint timelines.
5. Use **Configure** to change SUT, retention, tests, or order (panel closes after save).
6. Optional: **Analyze** (scenario / fingerprint / failed run) when `OPENAI_API_KEY` is set.

## Scenario configuration

| Setting | Purpose |
|---------|---------|
| **SUT version** | Labels runs for flakiness grouped by system-under-test version |
| **History max runs / days** | How many run records stay in the history window (`max_runs` ∩ `max_days`) |
| **Artifact max runs / days** | Independent disk cleanup for logs/snapshots under `artifacts/` |
| **Keep ≥1 failed in history** | Also keep the newest failed run still inside the history window (even if older than artifact max runs) |
| **Test order** | Execution order; reorder with ↑ / ↓ or by re-adding |

History and artifacts are pruned on new runs (and artifact settings apply immediately on configure-save).

## Automated tests

```bash
cd packages/contracts && uv run pytest
cd services/api && uv run pytest
cd services/executor && uv run pytest
```

## Environment

| Variable | Default | Used by |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+psycopg://…` (compose) / SQLite in tests | API |
| `REDIS_URL` | `redis://localhost:6379/0` | API, executor |
| `API_URL` | `http://localhost:8001` | executor (catalog registration) |
| `API_PORT` | `8001` | API |
| `WORKER_COUNT` | `2` | executor pool size |
| `VITE_API_URL` | *(unset → `/api` proxy)* | web |
| `OPENAI_API_KEY` | *(unset → heuristic analysis)* | API AI analyzer |
| `ANALYSIS_MODE` | *(auto)* | set `heuristic` to force non-LLM analysis |
| `AUTH_ADMIN_USERNAME` | `admin` | API login (optional override) |
| `AUTH_ADMIN_PASSWORD` | *(required)* | API login secret |
| `AUTH_VIEWER_USERNAME` | `viewer` | API login (optional override) |
| `AUTH_VIEWER_PASSWORD` | *(required)* | API login secret |
| `AUTH_SECRET` | *(required)* | signs HTTP-only login sessions |
| `AUTH_SESSION_TTL_SECONDS` | `28800` | login lifetime (8 hours) |
| `AUTH_COOKIE_SECURE` | `true` | HTTPS-only cookie; compose sets `false` locally |
| `ARTIFACTS_DIR` | `<repo>/artifacts` | API + executor |
| `S3_BUCKET` | *(unset → local artifacts)* | API + executor |
| `S3_ENDPOINT_URL` | *(required with `S3_BUCKET`)* | API + executor |
| `S3_ACCESS_KEY_ID` | *(required with `S3_BUCKET`)* | API + executor |
| `S3_SECRET_ACCESS_KEY` | *(required with `S3_BUCKET`)* | API + executor |
| `S3_REGION` | `auto` | API + executor |
| `AWS_ENDPOINT_URL`, `AWS_S3_BUCKET_NAME`, `AWS_DEFAULT_REGION` | Railway Bucket aliases | API + executor |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Railway Bucket credentials | API + executor |

When either the `S3_*` variables or Railway's generic `AWS_*` variables are present, artifacts
are stored in an S3-compatible bucket. Without a bucket variable, local filesystem storage
remains active for development and Docker Compose.

### Demo access roles

- `admin` can create, configure, run, analyze, export, and delete scenarios.
- `viewer` can browse results, run existing scenarios, launch AI analysis, and download reports/artifacts. Create, configure, and delete operations are rejected by the API and disabled in the UI.
- Login state is stored in a signed, HTTP-only, `SameSite=Lax` cookie. Production starts only when both passwords and `AUTH_SECRET` are configured.
- Executor callbacks remain private service-to-service endpoints and are blocked by the public nginx gateway.

The credentials in `docker-compose.yml` are development-only defaults. Never reuse them in Railway or another public environment.

Contracts version must match between API and executor (`CONTRACTS_VERSION`, currently **0.8.0**). Structured plugin logs additionally declare `LOG_SCHEMA_VERSION` (currently **1.0**) in the plugin manifest. Restart API and executor after upgrading either contract.

Structured logs are stored as canonical JSON artifacts, never in a framework-specific shape. Plugins map pytest, Playwright, API-client, or integration-runner output to `StructuredLogEntry` before storage. The dashboard requests logs only through semantic API routes:

- `GET /runs/{run_id}/tests/{test_id}/logs`
- `GET /runs/{run_id}/tests/{test_id}/steps/{step_id}/logs`

The API owns artifact lookup, authorization, schema validation, and legacy-log adaptation. The web app owns presentation: human-readable Console lines, structured-tree inspection, and derived TXT/JSON downloads. TXT is generated on demand and is not duplicated in artifact storage.

## Slice status

| Slice | Focus | Status |
|-------|--------|--------|
| 1 / 1.1 | Vertical slice: UI ↔ API ↔ Redis ↔ executor ↔ Google example | Done |
| 1.2 | History, flakiness, SUT/FW versions, timelines, fingerprints | Done |
| 1.3 | JustJoinIT + YouTube example tests | Done |
| 1.4 | AI failure analysis (GWT reports, async jobs, ZIP export) | Done |
| Polish | Scenario configure UI, test reorder, artifact retention | In progress / demo |
| Auth | Admin/viewer sessions and server-side authorization | Done |
| Later | CI, schedule, self-heal | Backlog |

## Capabilities overview

- Plugin handshake via `POST /plugins/manifest` (contracts version gate)
- Ordered multi-test scenarios with configure/create sharing the same form
- Run history + flakiness + fingerprint timelines
- Separate **artifact retention** (max runs, max days, keep-failed-only)
- Structured logs in the UI (`test.log.json` / `step.log.json`)
- Manual AI analysis scopes: scenario, fingerprint, or single run
