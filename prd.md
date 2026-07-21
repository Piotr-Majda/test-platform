# Test Platform — Product Requirements

Portfolio / learning product: orchestrate pluggable tests, show live results in a clean UI, persist history, and support AI-assisted failure analysis. Evolve the **existing** codebase slice by slice — do not rebuild from zero.

After each vertical slice, verify together before continuing.

## Goals

- Orchestrate and run tests on demand (user action), and later on schedule or from CI events.
- Clean React + Vite UI to inspect catalog, scenarios, runs, steps, logs, artifacts, history, and analysis.
- Backend: FastAPI + SQLAlchemy with **PostgreSQL** as the system database.
- Persist runs and events that happen during execution.
- Show step status (success / failed / not run), errors, traces, and allow analysis of failures.
- AI analysis: classify root cause, suggest fixes, and describe how to reproduce (manual trigger first).
- Event-driven communication between the platform and a pluggable **test executor** (common contracts / models; concrete transport is an implementation detail).
- Executor runs as a **worker pool** that can scale with queued work (not shut down after each task).
- Test framework based on pytest: scenarios built from DDD-style steps; adapters implement concrete I/O; steps stay abstract and maintainable.
- Example tests (already in scope / delivered as demos): Google title, JustJoinIT Python roles, YouTube AI Engineer latest video summary.
- Clean architecture: SOLID, YAGNI, DRY. Prefer TDD: Given / When / Then, one assertion focus per test; write the minimum code to pass a failing test.
- Packaging: Docker Compose now; Kubernetes later. Integrate with cloud hosting and CI/CD so the platform can validate a system under test (SUT).
- Python packages managed with **uv**.

## Versions

- **Framework version** — reported by the executor/plugin when it registers.
- **SUT version** — supplied by CI (or set manually on a scenario for local/demo use).

Full CI loop (CI triggers a run with a new SUT version and receives an automated report back) is **after** the public demo.

## UI

- Tests appear after an executor plugin registers its catalog (dynamic discovery).
- Users create scenarios by composing tests (drag-and-drop / configure), set retention and SUT version, run, and inspect results.
- Public portfolio demo (first release): **read-only** UI plus a short **video** of a run in action.
- Later: **password-gated** / temporary session access so invited users can trigger runs safely.

## Delivery principles

1. Implement feature by feature, top to bottom (UI ↔ API ↔ persistence ↔ executor ↔ framework ↔ example), then validate locally.
2. Ask for human verification before expanding scope.
3. Prefer small, testable modules and dependency injection at boundaries.

## Deploy & demo

- Application must be containerized and deployable publicly for a CV/portfolio link (not only the repository).
- First public hosting may be **cheap / sleeping** (wake on visit) — enough for demo traffic.
- Compose services for demo: web, API, PostgreSQL, event bus infrastructure, and executor worker pool.

## Out of scope for first public demo (later)

- Scheduled runs (background scheduler / CRON-style jobs).
- CI firmware/SUT handshake + report-back to the pipeline.
- Password-gated interactive runs (after read-only demo).
- Kubernetes.

## Nice to have (end)

- **Self-heal / agent-maintained steps**: agents adapt steps when the SUT UI/API changes, with minimal human in the loop. Explicitly **not** required for the portfolio demo.
