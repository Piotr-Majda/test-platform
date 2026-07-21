# Test Platform v2 — Project Summary

Source of truth for product decisions. Derived from `prd.md` and clarification sessions.

## Product goal

Orchestrate and run pluggable pytest-based tests, show live step/status/logs in a React UI, persist runs/events (SQLite now; Postgres later), communicate via Redis Streams, then AI failure analysis and agent-maintained test steps.

## Slice 1 / 1.1 — done

- UI: discovery, DnD scenarios, step table, nested `step.log.json` artifacts
- API + Redis Streams + N-worker pool
- Hybrid pytest engine (`@step` + hooks + contextvar emitter)
- Adapter artifact strategy (HTML on failure only)
- Examples: `google_title`, demo `flaky_coin`

## Slice 1.2 — done (history & analysis UI)

- Run history + flakiness by `(test_id, sut_version, framework_version)`
- SUT version + retention (`max_runs` ∩ `max_days`) on scenario; prune on new run
- Framework/plugin version stamped on each run
- SUT-focused step/test/run durations (`timed_action`)
- Reliability label (stable ≤10% / watch / flaky) vs duration trend (faster/slower/steady)
- Error fingerprints (persisted across prune) + shared run/fingerprint timelines (pass/fail dots, SUT/FW chips)
- Run status: deduped single-execution steps; expandable error column

## Slice 1.3 — example tests (done)

- **JustJoinIT** (`justjoin_python_roles`) — live API → 10 unique Python-titled roles + URL GET 200 on first 3; unit tests mocked (`PLATFORM_FAKE_JJIT=1`)
- **YouTube** (`youtube_ai_engineer_latest`) — AI Engineer channel RSS → newest video + watch URL 200 + extractive summary; mock with `PLATFORM_FAKE_YOUTUBE=1`

## Slice 1.4 — AI failure analysis (implemented; verify in UI)

Manual trigger only (token control; auto later optional).

**Buttons / scopes**
| UI entry | Scope | Context |
|----------|--------|---------|
| Scenario | Whole scenario history (retention window) | All tests; list of current errors; flakiness from history |
| Fingerprint | That error pattern | Occurrences in scenario history + last failure link |
| Test run | Single run | Events / steps / artifacts for that run only |

**Structured report (`AnalysisReport` v2)**
- Header: scenario name · infra · SUT · FW
- `errors[]` GWT: **Given** (context/setup), **When** (step path to failure), **Then**, **Expected**
- Plus: root_cause_name, confidence_pct, error_type, components[], last_failure_run_id, actions
- `flakiness[]` from scenario history (not invented by LLM)
- Export: `GET /analyses/{id}/export` → ZIP (`report.md` + `report.json` + artifacts)

**Stack:** pydantic-ai agent + injectable analyzer port (heuristic in tests; LLM when API key set)

## Demo polish — scenario config & artifact retention

- Shared create/configure UI (panel closes after save)
- Reorder scenario tests (↑ / ↓) + add tests when editing
- **Artifact retention** independent of history: `max_runs`, `max_days`, `keep_at_least_one_failed`
- Keep last N artifact runs; optionally also keep newest failed still inside history window
- Contracts **0.7.1** (`ArtifactRetentionConfig` on `Scenario`)

## Later (after polish)

- Postgres (replace SQLite default)
- Docker Compose → K8s / CI-CD
- CI dynamic SUT on execute event
- Schedule / auth / scale-to-zero workers
- Agent-maintained steps (self-heal framework)

## Locked technical decisions

| Topic | Decision |
|--------|----------|
| Event bus | Redis Streams |
| Execution | Hybrid pytest + DDD steps |
| History storage | Enrich runs; no second copy of logs |
| History retention | `max_days` ∩ `max_runs` |
| Artifact retention | Separate config; optional keep-failed-only |
| Flakiness / reliability | fail_rate; stable ≤ 0.10 |
| Fingerprints | step + exception type + normalized message; persist occurrences |
| SUT version | Scenario field now; CI event later |
| Framework version | PluginManifest → stamped on run |
| Plugin handshake | `POST /plugins/manifest` with versioned `PluginManifest` |
| Setup topology | One Test Platform + One Framework + One SUT per deployment |
| Contracts version | Must match on register (409 on mismatch); upgrade both sides together |
| Catalog sync | Manifest replaces that plugin’s test list (source of truth) |
| Local DB | SQLite for now; Postgres with Docker/CI later |
| AI stack (1.4) | pydantic-ai + analyzer port (DI); manual trigger |
| Analysis scopes | scenario \| fingerprint \| run |
| Analysis errors window | Distinct fingerprints in scenario retention history |
| Python package manager | uv |

## Architecture (current)

```
Framework connect → PluginManifest { plugin_id, framework_version, contracts_version, tests[] }
  → API persists catalog for UI (GET /tests)

Scenario { sut_version, max_runs, max_days }
  → Run { sut_version, framework_version, status, duration_ms, events... }
  → FingerprintOccurrence (survives prune)
  → History API: flakiness + fingerprints.timeline + timelines in UI
  → prune runs after each new run
  → Manual Analyze → AnalysisReport (errors list + flakiness snapshot)
```

## Delivery cadence

Build one vertical slice → you manually verify → only then next feature.

## Definition of done

**1.2 (accepted):** SUT + retention, history, flakiness, timelines, fingerprints, automated prune/flakiness tests.

**1.3:** Both JustJoinIT and YouTube tests runnable from UI via DnD scenarios; unit tests pass; you verify E2E.

**1.4:** Manual Analyze on scenario / fingerprint / run; structured `AnalysisReport` in UI; unit tests with fake analyzer.
