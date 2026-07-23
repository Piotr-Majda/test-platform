# Test Platform

Public demo platform for composing and running pluggable pytest tests, observing live
results, retaining execution history and artifacts, and analyzing failures with optional AI.

- Live demo: [test-platform-demo.up.railway.app](https://test-platform-demo.up.railway.app/)
- Current architecture decisions and delivery status: [project-summary.md](project-summary.md)
- Product vision, requirements, and roadmap: [prd.md](prd.md)

## Documentation ownership

Use this README for the current implementation, local setup, and operation. Use
`project-summary.md` for accepted technical decisions and known constraints. Use `prd.md`
for product intent and future scope. If they disagree about what exists today, this README
and the code are authoritative.

## Current capabilities

- Dynamic test catalog registered by an executor plugin.
- Ordered, multi-test scenarios with SUT version and separate history/artifact retention.
- Long-lived Redis-backed worker pool. Different runs may execute concurrently; tests
  inside one scenario run execute in their configured order.
- Live run/test/step status, errors, artifacts, durations, history, flakiness, reliability,
  trends, and error fingerprints.
- Versioned, framework-neutral structured logs with test- and step-level Console views.
  The UI can derive and download TXT or download canonical JSON.
- Manual analysis for a scenario, fingerprint, run, or single test. Reports can be
  downloaded as ZIP files with JSON, Markdown, and referenced artifacts.
- Signed HTTP-only sessions with `admin` and `viewer` roles.
- Responsive React UI for desktop and narrow/mobile screens.
- Local Docker Compose stack and a public HTTPS Railway deployment.

## Repository layout

| Path | Role |
|------|------|
| `packages/contracts` | Versioned Pydantic messages, models, log schema, and Redis Stream helpers |
| `services/api` | FastAPI orchestration API, SQLAlchemy, Alembic, analysis, auth, and artifact access |
| `services/executor` | Pluggable pytest executor, DDD-style `@step` framework, adapters, and worker pool |
| `apps/web` | React + Vite dashboard and nginx public gateway |
| `scripts` | E2E and artifact-download smoke checks |

## Runtime architecture

```text
Browser
  -> public web/nginx (HTTPS on Railway)
       -> React static files
       -> /api/* proxy
            -> private FastAPI service
                 -> PostgreSQL (platform state)
                 -> Redis Streams (execute commands and progress events)
                 -> S3-compatible bucket or local filesystem (artifacts)

Private executor service
  -> registers PluginManifest with the API
  -> consumes execute commands from Redis
  -> runs pytest tests through steps and adapters
  -> publishes progress events to Redis
  -> writes structured logs and other artifacts
```

On Railway, only the web service has a public domain. API and executor communication uses
the private service network. nginx does not expose plugin registration or executor event
callback routes. Railway configuration is managed in Railway rather than committed as a
`railway.toml`.

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node 20+
- PostgreSQL 16+
- Redis 7+

PostgreSQL is the system database and is managed with Alembic. API unit tests use
in-memory SQLite. Redis is required for real run orchestration.

## Install

```bash
cd packages/contracts
uv sync

cd ../../services/api
uv sync

cd ../executor
uv sync

cd ../../apps/web
npm install
```

## Run locally

The full Docker Compose stack is the simplest demo setup:

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| UI | http://localhost:8080 |
| Direct API docs | http://localhost:8001/api/docs |
| API health | http://localhost:8001/health |
| PostgreSQL | `localhost:5432` (`platform` / `platform` / `platform`) |
| Redis | `localhost:6379` |

The API container applies `alembic upgrade head` before startup. PostgreSQL data is stored
in `platform-pg`; local artifacts are shared by API and executor in `platform-data`.

Development-only logins from `docker-compose.yml`:

- admin: `admin` / `admin-demo`
- viewer: `viewer` / `viewer-demo`

Never use these credentials in a public environment.

Stop containers while retaining data:

```bash
docker compose down
```

Delete local demo volumes too:

```bash
docker compose down -v
```

### Run services directly

First start infrastructure:

```bash
docker compose up -d postgres redis
```

Then use separate PowerShell terminals.

API:

```powershell
cd services/api
$env:DATABASE_URL = "postgresql+psycopg://platform:platform@localhost:5432/platform"
$env:AUTH_ADMIN_PASSWORD = "admin-demo"
$env:AUTH_VIEWER_PASSWORD = "viewer-demo"
$env:AUTH_SECRET = "local-development-secret-change-me"
$env:AUTH_COOKIE_SECURE = "false"
uv run alembic upgrade head
uv run test-platform-api
```

Executor:

```powershell
cd services/executor
uv run test-platform-executor
```

Web:

```powershell
cd apps/web
npm run dev
```

Open http://localhost:5173. Vite sends browser API calls through its `/api` proxy. The
executor talks directly to `http://localhost:8001`.

## Quick demo flow

1. Log in as `viewer` to explore the public demo, or as `admin` to manage scenarios.
2. Open an existing scenario and run it.
3. Watch run, test, and step status update; inspect errors, artifacts, and Console output.
4. Open History to inspect reliability, duration trends, flakiness, and fingerprints.
5. Trigger analysis for a run, test, scenario, or fingerprint and download its report.
6. As admin, create or configure a scenario, reorder tests, and set retention.

The catalog currently includes example Google, flaky-coin, JustJoinIT, and YouTube tests.
Network-dependent examples can fail when their external target changes or is unavailable;
that behavior is intentionally visible in history and analysis.

## Roles

| Action | Admin | Viewer |
|--------|:-----:|:------:|
| Browse scenarios, runs, history, logs, and artifacts | Yes | Yes |
| Run an existing scenario | Yes | Yes |
| Trigger analysis and download reports/artifacts | Yes | Yes |
| Create or configure a scenario | Yes | No |
| Delete a scenario | Yes | No |

The UI hides or disables unavailable actions, and the API enforces the same authorization.
Sessions are signed and stored in an HTTP-only, `SameSite=Lax` cookie. Production cookies
must be HTTPS-only.

## Scenario configuration and retention

| Setting | Purpose |
|---------|---------|
| **SUT version** | Labels runs and scopes history metrics to a system-under-test version |
| **History max runs / days** | Keeps the intersection of the newest `max_runs` and runs within `max_days` |
| **Artifact max runs / days** | Independently cleans logs, snapshots, screenshots, and other artifacts |
| **Keep at least one failed** | Preserves the newest failed artifact set still inside the history window |
| **Test order** | Defines sequential execution order inside the scenario run |

History and artifacts are pruned when a run starts. Saving changed artifact retention also
applies pruning immediately.

## Versioned plugin and log contracts

The executor registers:

```text
PluginManifest {
  plugin_id,
  framework_version,
  contracts_version,
  log_schema_version,
  tests[]
}
```

`CONTRACTS_VERSION` must match between API and executor (currently **0.8.0**).
`LOG_SCHEMA_VERSION` must also match (currently **1.0**). Registration returns HTTP 409
on a mismatch; upgrade and restart both services together.

Plugins normalize pytest, Playwright, API-client, or integration-runner output to
`StructuredLogEntry` before storage. The canonical entry contains:

```text
timestamp, layer, component, level, message, duration_ms, event, data, children
```

The dashboard reads logs only through the authenticated API:

- `GET /runs/{run_id}/tests/{test_id}/logs`
- `GET /runs/{run_id}/tests/{test_id}/steps/{step_id}/logs`

The API owns authorization, artifact lookup, schema validation, and adaptation of legacy
logs. The UI owns formatting, layer filtering, structured-tree presentation, and derived
TXT/JSON downloads. TXT is generated on demand and is not duplicated in storage.

## Artifact storage

Without bucket settings, API and executor use `ARTIFACTS_DIR`. When bucket variables are
present, both services use S3-compatible object storage. The Railway deployment uses a
Railway Bucket; it does not require a separate AWS account.

| Variable | Default / meaning | Used by |
|----------|-------------------|---------|
| `ARTIFACTS_DIR` | `<repo>/artifacts` | API, executor |
| `S3_BUCKET` | unset means local storage | API, executor |
| `S3_ENDPOINT_URL` | S3-compatible endpoint | API, executor |
| `S3_ACCESS_KEY_ID` | bucket access key | API, executor |
| `S3_SECRET_ACCESS_KEY` | bucket secret | API, executor |
| `S3_REGION` | `auto` | API, executor |
| `AWS_ENDPOINT_URL`, `AWS_S3_BUCKET_NAME`, `AWS_DEFAULT_REGION` | Railway Bucket aliases | API, executor |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Railway Bucket credentials | API, executor |

The browser never reads the bucket directly; all artifact and log access goes through the
API.

## Other environment variables

| Variable | Default / meaning | Used by |
|----------|-------------------|---------|
| `DATABASE_URL` | local PostgreSQL URL when omitted | API |
| `REDIS_URL` | `redis://localhost:6379/0` | API, executor |
| `API_URL` | `http://localhost:8001` | executor |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8001` | API |
| `PLUGIN_ID` | `example-executor` | executor |
| `WORKER_COUNT` | `2` | executor |
| `VITE_API_URL` | unset uses `/api` | web build |
| `OPENAI_API_KEY` | unset uses heuristic analysis | API |
| `ANALYSIS_MODE` | auto; `heuristic` forces non-LLM analysis | API |
| `ANALYSIS_MODEL` | `openai:gpt-4o-mini` | API |
| `AUTH_ADMIN_USERNAME` | `admin` | API |
| `AUTH_ADMIN_PASSWORD` | required | API |
| `AUTH_VIEWER_USERNAME` | `viewer` | API |
| `AUTH_VIEWER_PASSWORD` | required | API |
| `AUTH_SECRET` | required session-signing secret | API |
| `AUTH_SESSION_TTL_SECONDS` | `28800` (8 hours) | API |
| `AUTH_COOKIE_SECURE` | `true`; Compose sets `false` | API |

## Database migrations

From `services/api`:

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

## Verification

```bash
cd packages/contracts
uv run pytest

cd ../../services/api
uv run pytest

cd ../executor
uv run pytest

cd ../../apps/web
npm run lint
npm run build
```

The repository currently contains 93 Python tests: 13 contracts, 52 API, and 28 executor.

## Delivery status

| Area | Status |
|------|--------|
| Catalog, scenarios, Redis orchestration, pytest executor, worker pool | Done |
| History, retention, trends, flakiness, fingerprints | Done |
| Example UI/API/integration-style tests | Done |
| Manual heuristic/AI analysis and export | Done |
| Admin/viewer authentication and private API gateway | Done |
| Responsive/mobile dashboard | Done |
| Versioned test/step Console logs with TXT/JSON download | Done |
| Public Railway HTTPS deployment with PostgreSQL, Redis, and bucket | Done |
| Scheduling/CRON, CI event handshake/report-back, Kubernetes, self-heal | Backlog |
