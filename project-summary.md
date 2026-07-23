# Test Platform — Architecture and Project Summary

This document records the current architecture, accepted technical decisions, delivery
status, constraints, and unresolved choices. Product intent and future requirements live
in [prd.md](prd.md); operational setup lives in [README.md](README.md).

## Product outcome

The platform composes dynamically discovered pytest tests into ordered scenarios, executes
them through a long-lived worker pool, streams progress to a responsive dashboard, stores
history and artifacts, and supports human-readable logs plus optional AI-assisted failure
analysis.

The current public demo is a modular monolith around one orchestration API, with separate
web and executor processes and managed infrastructure. This keeps the domain model and API
contract in one place without coupling test execution to the dashboard process.

## Current deployment

- Public HTTPS web/nginx gateway:
  [test-platform-demo.up.railway.app](https://test-platform-demo.up.railway.app/)
- Private FastAPI orchestration service.
- Private executor service with a configurable worker pool.
- Railway PostgreSQL for platform state.
- Railway Redis for commands and progress events.
- Railway Bucket, through its S3-compatible interface, for persistent artifacts.
- Railway service variables and networking are configured in Railway, not committed to the
  repository.

Docker Compose provides the equivalent local topology with local PostgreSQL, Redis, and a
shared artifact volume.

## Delivered slices

### Core orchestration

- Executor registers a dynamic catalog through a versioned `PluginManifest`.
- Admins compose and reorder tests in a scenario and set its SUT version.
- API creates a run and publishes an `ExecuteTestCommand` to Redis Streams.
- Long-lived executor workers consume commands through a Redis consumer group.
- Tests inside one scenario run execute sequentially; separate run commands can execute
  concurrently up to `WORKER_COUNT`.
- pytest hooks and context-local event emission project run/test/step status into the API.
- Example tests cover browser/UI, external HTTP/API, integration-style, and deterministic
  flaky behavior.

### History and retention

- Run history and flakiness are grouped by `(test_id, sut_version, framework_version)`.
- Reliability is derived from failure rate: stable at `<= 10%`, then watch/flaky.
- Test and step duration trends are computed from retained history.
- Error fingerprints combine step, exception type, and normalized message.
- Fingerprint occurrences survive run-history pruning.
- Run history uses the intersection of `max_runs` and `max_days`.
- Artifact retention is independent and can preserve the newest failed artifact set that
  remains inside the scenario history window.

### Analysis

Analysis is manual to control cost. Four scopes are implemented:

| Scope | Evidence boundary |
|-------|-------------------|
| `scenario` | Retained scenario history, current errors, fingerprints, and flakiness |
| `fingerprint` | One error pattern and its occurrences in retained scenario history |
| `run` | Events, tests, steps, and artifacts from one run |
| `test` | Events, steps, and artifacts for one test in one run |

`AnalysisReport` contains GWT-style failure context, root-cause classification,
confidence, components, reproduction path, recommended actions, health signals, and
history-derived flakiness where applicable. Run analysis rolls up saved per-test analyses.
Exports are ZIP files containing Markdown, JSON, and referenced artifacts.

The analyzer is behind a dependency-injected port. It uses heuristic analysis when no
OpenAI key is configured and `pydantic-ai` when enabled.

### Authentication and public demo

- Two roles: `admin` and `viewer`.
- Admin has full scenario management.
- Viewer can browse, run existing scenarios, analyze, and download; viewer cannot create,
  configure, or delete.
- Signed HTTP-only cookie sessions are enforced by the API.
- nginx is the only public service and proxies browser `/api/*` requests to the private API.
- Plugin registration and executor event callback routes are blocked at the public gateway.
- The UI is responsive on phone-sized and narrow screens.

### Structured Console logs

- Plugins emit framework-neutral structured log documents instead of UI-specific text.
- `LOG_SCHEMA_VERSION` is negotiated in `PluginManifest`.
- API rejects incompatible contract or log-schema versions with HTTP 409.
- Canonical log entries include timestamp, layer, component, level, message, duration,
  event metadata, data, and nested children.
- API resolves artifacts, validates/adapts documents, and exposes semantic test/step log
  endpoints.
- UI renders Console text and a structured tree, filters by layer, and derives TXT/JSON
  downloads. The UI does not know bucket paths or framework-specific log formats.

## Architecture

```text
                    public HTTPS
Browser --------------------------------> web/nginx
                                             |
                                  React files | /api proxy
                                             v
                                      private FastAPI
                                       /      |      \
                         system state /       |       \ artifact reads
                                     v        v        v
                               PostgreSQL   Redis   S3-compatible
                                            Streams      bucket
                                              ^
                        commands and events   |
                                              |
                                      executor pool
                                      /     |      \
                                   pytest  steps  adapters
```

### Main flow

```text
Plugin startup
  -> POST /plugins/manifest
  -> version gates
  -> replace that plugin's catalog

User starts scenario
  -> API persists queued Run
  -> Redis ExecuteTestCommand
  -> executor worker runs ordered tests
  -> Redis progress events
  -> API persists events and projections
  -> executor writes artifacts
  -> UI polls authenticated API for live state

User opens Console
  -> semantic API log request
  -> API reads local/S3 artifact and validates schema
  -> UI renders human or structured view
  -> optional TXT/JSON download
```

## Accepted design decisions

| Topic | Decision and reason |
|-------|---------------------|
| Platform shape | Modular monolith plus separate executor. One API owns the domain and persistence; execution can scale independently without premature microservices. |
| Event transport | Redis Streams. Consumer groups, acknowledgements, and replay fit queued run execution better than synchronous HTTP; less operational weight than Kafka for this scale. |
| Execution | Hybrid pytest plus DDD-style steps and adapters. Existing pytest/Playwright ecosystems remain usable while business steps stay reusable and test data stays separate from I/O details. |
| Concurrency | Long-lived N-worker pool. Multiple runs can proceed concurrently; ordered tests within a run stay deterministic. |
| System database | PostgreSQL with Alembic migrations. SQLite is restricted to isolated API tests. |
| Artifact storage | Port with local-filesystem and S3-compatible implementations. Railway Bucket provides persistent cloud storage without an AWS account. |
| Browser/API boundary | nginx serves the SPA and proxies `/api`; the API has no public Railway domain. This avoids CORS exposure and keeps executor callbacks private. |
| Authentication | Signed HTTP-only sessions with server-side role enforcement. Simpler and safer for an invited demo than browser-stored bearer tokens or a full identity provider. |
| Contracts | Shared Pydantic package with explicit `CONTRACTS_VERSION` and `LOG_SCHEMA_VERSION`; incompatible plugins fail fast at registration. |
| Catalog ownership | Each plugin manifest replaces that plugin's test catalog. The plugin remains the source of truth for its discovered tests. |
| Log boundary | Plugins normalize to canonical JSON; API owns retrieval/compatibility; UI owns presentation. This keeps storage and framework details out of the UI. |
| History | Enrich persisted runs and events instead of maintaining a second log copy. |
| History retention | Intersection of `max_days` and `max_runs`, applied per scenario. |
| Artifact retention | Separate policy because large binaries and logs have different cost/diagnostic value from database history. |
| Fingerprints | Step + exception type + normalized message, with occurrences retained separately from prunable runs. |
| Analysis | Manual asynchronous job, analyzer port, deterministic heuristic fallback. This controls token cost and keeps tests independent of an LLM. |
| Python tooling | `uv` for reproducible, fast package and virtual-environment management. |
| Cloud configuration | Railway UI/service variables rather than repository-specific deployment files, matching the chosen operational workflow. |

## Current constraints

- A scenario chooses framework version from the plugin that owns its first test. The API
  does not yet validate or route a scenario containing tests from multiple plugins.
- The demo runs one executor plugin service, although the catalog model stores `plugin_id`
  and can retain catalogs for more than one registered plugin.
- Worker threads scale concurrency inside one executor instance; distributed autoscaling,
  lease recovery, and dead-letter handling are not implemented.
- Analysis jobs are manual and are not yet backed by a durable job scheduler.
- External demo tests depend on third-party sites and feeds, so their live behavior can
  change independently of the platform.

## Version baseline

| Contract | Current value |
|----------|---------------|
| Executor framework | `0.1.1` |
| Shared platform contract | `0.8.0` |
| Structured log schema | `1.0` |

Executor changes that can alter catalog entries, step IDs, execution semantics, or outcomes
require a version increment and an entry in `services/executor/CHANGELOG.md`. The registered
version is stamped on every run, preserving the boundary between historical behaviors.

The repository currently contains 93 Python tests: 13 contracts, 52 API, and 28 executor,
plus frontend lint and production-build checks.

## Delivery status

| Capability | Status |
|------------|--------|
| Core vertical slice and dynamic catalog | Done |
| Scenario configuration and ordered execution | Done |
| History, retention, trends, flakiness, fingerprints | Done |
| Example Google, JustJoinIT, YouTube, and flaky tests | Done |
| Four-scope analysis and report export | Done |
| PostgreSQL/Alembic and S3-compatible artifact storage | Done |
| Admin/viewer demo access and private API gateway | Done |
| Responsive/mobile UI | Done |
| Versioned test/step Console | Done |
| Railway public HTTPS deployment | Done |
| Scheduler/CRON and event-triggered runs | Backlog |
| CI SUT-version handshake and report-back | Backlog |
| Kubernetes/distributed worker operation | Backlog |
| Reviewed self-healing changes | Backlog |

## Open product decisions

These choices are not settled by the current code and should not be presented as locked:

1. **Primary product direction:** remain a public portfolio/demo platform, or evolve into
   an internal multi-team/multi-tenant product.
2. **Scheduling ownership:** implement a native scheduler in the platform, or delegate
   schedules to Jenkins/another CI orchestrator.
3. **CI ownership:** make the platform's API/webhooks the primary pipeline interface, or
   model Jenkins as a first-class service that owns triggering and callbacks.
4. **Plugin topology:** preserve one executor/plugin per deployment, or support explicit
   routing of one scenario across multiple registered plugins/executor pools.

Until these are decided, the PRD treats them as roadmap questions rather than current
commitments.
