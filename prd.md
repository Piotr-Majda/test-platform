# Test Platform — Product Requirements

## Product vision

Build an approachable test orchestration and observability platform that lets a user
compose pluggable tests, run them from a dashboard or CLI/CI, understand failures quickly,
and keep test code independent from test data and concrete UI/API adapters.

The product evolves the existing pytest-based codebase in vertical slices. It should reuse
the wider pytest and Playwright ecosystems rather than replace them with a proprietary test
runner.

## Product stage

The current product is a public, password-gated portfolio demo hosted on Railway. Invited
users can interact with existing scenarios rather than only watch a read-only recording.
The current implementation is single-organization and demo-oriented; multi-team or
multi-tenant production operation has not been selected as a requirement.

## Target users

- **Viewer/demo guest:** wants to explore scenarios and results, run a prepared demo,
  inspect/download logs and reports, and trigger analysis.
- **Test developer/admin:** wants to register tests, compose/configure scenarios, manage
  retention, run tests, diagnose failures, and delete obsolete scenarios.
- **CI pipeline (future):** wants to submit a SUT version/build event, trigger selected
  tests, await a result, and consume a machine-readable report.

## Goals

- Run ordered UI, API, and integration-style test scenarios on demand.
- Later trigger runs from schedules and CI/build events.
- Keep the platform compatible with pytest-based plugins and Playwright/browser adapters.
- Separate scenario intent, reusable steps, test data, and concrete adapters.
- Discover tests dynamically from versioned plugin manifests.
- Show live run, test, and step status with errors, durations, artifacts, and Console logs.
- Persist history and calculate reliability, flakiness, duration trends, and fingerprints.
- Retain database history and large artifacts with independent policies.
- Provide manual, evidence-bounded heuristic or AI-assisted failure analysis.
- Export reports and artifacts for human or CI consumption.
- Support concurrent run processing through a scalable worker pool.
- Keep the API private behind the web gateway in public deployments.
- Work well on desktop and narrow/mobile screens.
- Package Python services with `uv` and deploy all components as containers.

## Current functional requirements

### Catalog and scenarios

- Executor/plugin registers `plugin_id`, framework version, shared contract version, log
  schema version, and test definitions.
- Platform rejects incompatible manifest versions.
- Admin can create, configure, reorder, and delete scenarios.
- Scenario contains a name, ordered test IDs, SUT version, history policy, and artifact
  policy.
- Viewer can browse and execute existing scenarios but cannot mutate them.

### Execution and observation

- Starting a scenario creates a persistent queued run and publishes an event-driven command.
- A long-lived worker pool executes multiple run commands concurrently.
- Tests in one scenario run execute in configured order.
- Dashboard presents current run/test/step state, errors, traces, and durations.
- Execution artifacts may include structured logs, HTML snapshots, screenshots, and other
  framework outputs.

### History

- Users can inspect retained runs and per-test/per-step outcomes.
- Platform calculates failure rate and reliability for each test/SUT/framework combination.
- Platform shows duration trends and fingerprint timelines.
- History and artifact retention can be configured independently per scenario.

### Console logs

- Plugins map their native output to a versioned, framework-neutral JSON log contract.
- API is the only browser-facing interface to stored logs and artifacts.
- Users can open a Console for a whole test or an individual step.
- UI renders human-readable lines from timestamp, component/layer, message, and duration.
- Users can inspect structured entries and download derived TXT or canonical JSON.

### Failure analysis

- Analysis is explicitly triggered by a user.
- Supported scopes are scenario, fingerprint, run, and test.
- Analysis must remain inside the selected evidence boundary and must not invent history.
- Output includes GWT context, likely root cause, confidence, classification, components,
  reproduction guidance, recommended actions, and log-health signals.
- LLM integration is optional; deterministic heuristic output remains available.
- Saved reports can be restored and downloaded with referenced artifacts.

### Access and public demo

- Authentication uses temporary signed sessions.
- Admin has scenario-management permission.
- Viewer has browse, run, analyze, and download permission.
- Both UI state and API authorization reflect the role.
- Public web service uses HTTPS.
- API and executor remain private services; executor callbacks are not exposed by nginx.

## Quality requirements

- Clear boundaries between contracts, orchestration, persistence, execution, adapters, and
  presentation.
- PostgreSQL schema changes use Alembic migrations.
- Structured contracts are validated with Pydantic and explicitly versioned.
- Test framework code favors reusable DDD-style steps and injected adapters over selectors
  or test data embedded in scenarios.
- Automated tests cover contracts, API/domain behavior, executor/framework behavior, auth,
  artifact storage, and log compatibility.
- UI passes lint and production build and remains usable at phone-sized widths.
- Secrets and demo credentials are supplied by the deployment environment and never
  committed for public use.

## Current deployment requirements

- Local development: Docker Compose with web, API, executor, PostgreSQL, Redis, and shared
  local artifact storage.
- Public demo: Railway services for web, API, executor, PostgreSQL, Redis, and an
  S3-compatible Railway Bucket.
- Only the web/nginx service receives a public domain.
- Public address:
  [test-platform-demo.up.railway.app](https://test-platform-demo.up.railway.app/)
- Railway is configured through its service UI and environment variables.
- Kubernetes is not required for the current demo.

## Delivered examples

- Google title browser test.
- Deterministic flaky-coin test for history and fingerprint demonstrations.
- JustJoinIT Python-role discovery and URL checks.
- YouTube AI Engineer feed/latest-video summary.

These examples demonstrate the plugin and observability model; they are not a guarantee of
availability for external third-party systems.

## Roadmap

### Next product capabilities

- Scheduled/CRON-style execution.
- Event-triggered execution for new builds or firmware/SUT versions.
- CI API/webhook contract, status polling/callback, and machine-readable report-back.
- Durable analysis/scheduling jobs and stronger failed-command recovery.

### Scale and extensibility

- Explicit routing when scenarios use tests from multiple plugins.
- Horizontal/distributed worker scaling and operational metrics.
- Kubernetes deployment only when workload or customer requirements justify it.
- Additional plugin adapters for other frameworks while preserving the shared contracts.

### Long-term

- Reviewed self-healing/agent-maintained steps that propose adapter or selector changes when
  a SUT changes. Changes must remain auditable and should not silently weaken assertions.

## Out of scope for the current public demo

- Native scheduling and CRON jobs.
- Complete CI SUT handshake and automated report-back.
- Multi-tenant identity, organization isolation, and enterprise SSO.
- Kubernetes and automatic distributed worker scaling.
- Unattended self-healing changes.

## Open decisions

Before designing the next major slice, decide:

1. Whether the long-term product is a portfolio demo or an internal multi-team platform.
2. Whether scheduling belongs inside Test Platform or in Jenkins/another external
   orchestrator.
3. Whether CI integrates directly with a platform API/webhook or through a first-class
   Jenkins service.
4. Whether deployments keep one executor/plugin or route scenarios across multiple plugin
   pools.

These questions do not block the current demo, but each changes the design of scheduling,
authorization, tenancy, and execution routing.
