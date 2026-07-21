"""Manual failure analysis — context pack + injectable analyzer (heuristic / LLM)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Protocol
import uuid

from test_platform_contracts import (
    CONTRACTS_VERSION,
    AnalysisReport,
    AnalysisRequest,
    AnalysisScope,
    ErrorAnalysisItem,
    FailureWhere,
    FlakinessSnapshot,
    HealthSignal,
    TestAnalysisRef,
    TestRunEvent,
    TestRunEventType,
)

from test_platform_api.db import SqlAlchemyRepository
from test_platform_api.history import (
    apply_occurrence_retention,
    compute_flakiness,
    error_fingerprint,
    normalize_error_message,
    reliability_label,
    test_outcome_from_events,
)
from test_platform_api.paths import artifacts_dir

LOG_BASELINE_N = 5
LOG_SIZE_RATIO_HIGH = 3.0
LOG_SIZE_RATIO_LOW = 0.2
LOG_TAIL_CHARS = 4000


@dataclass
class FingerprintOccurrenceView:
    run_id: str
    test_id: str
    step_id: str
    sut_version: str
    framework_version: str
    fingerprint: str
    label: str
    message: str
    created_at: datetime


@dataclass
class AnalysisContext:
    request: AnalysisRequest
    scenario_name: str = ""
    sut_version: str = "unknown"
    framework_version: str = "unknown"
    infra: str = "local"
    occurrences: list[FingerprintOccurrenceView] = field(default_factory=list)
    flakiness: list[FlakinessSnapshot] = field(default_factory=list)
    run_step_messages: list[tuple[str, str, str]] = field(default_factory=list)
    step_paths: dict[str, list[str]] = field(default_factory=dict)
    # test_id -> step path (for multi-test runs)
    test_step_paths: dict[str, list[str]] = field(default_factory=dict)
    failure_details: dict[str, tuple[str, str]] = field(default_factory=dict)
    log_excerpts: dict[str, str] = field(default_factory=dict)  # test_id -> excerpt
    health_signals: list[HealthSignal] = field(default_factory=list)


class FailureAnalyzer(Protocol):
    def analyze(self, context: AnalysisContext) -> AnalysisReport: ...


def validate_analysis_request(request: AnalysisRequest) -> None:
    if request.scope == AnalysisScope.SCENARIO and not request.scenario_id:
        raise ValueError("scenario_id required for scenario scope")
    if request.scope == AnalysisScope.RUN and not request.run_id:
        raise ValueError("run_id required for run scope")
    if request.scope == AnalysisScope.TEST:
        if not request.run_id or not request.test_id:
            raise ValueError("run_id and test_id required for test scope")
    if request.scope == AnalysisScope.FINGERPRINT:
        if not request.scenario_id or not request.fingerprint:
            raise ValueError("scenario_id and fingerprint required for fingerprint scope")


def step_path_until_failure(events: list[TestRunEvent], *, test_id: str | None = None) -> list[str]:
    """Ordered step ids for a test up to and including the first failed step."""
    path: list[str] = []
    for event in events:
        if event.event_type not in {
            TestRunEventType.STEP_FINISHED,
            TestRunEventType.STEP_FAILED,
        }:
            continue
        if test_id and event.test_id and event.test_id != test_id and event.test_id != "unknown":
            continue
        step_id = event.step_id or "unknown"
        path.append(step_id)
        if event.event_type == TestRunEventType.STEP_FAILED:
            break
    return path


def _load_run_step_meta(
    repo: SqlAlchemyRepository,
    run_id: str,
    *,
    test_id: str | None = None,
) -> tuple[list[str], dict[str, tuple[str, str]]]:
    events = repo.list_events(run_id)
    if test_id:
        path = step_path_until_failure(events, test_id=test_id)
        details: dict[str, tuple[str, str]] = {}
        for event in events:
            if event.event_type != TestRunEventType.STEP_FAILED:
                continue
            tid = event.test_id or test_id
            if tid != test_id and tid != "unknown":
                continue
            details[test_id] = (event.message, _expected_from_message(event.message, event.step_id or ""))
        return path, details

    test_ids = [e.test_id for e in events if e.test_id]
    primary = next((t for t in test_ids if t != "unknown"), test_ids[0] if test_ids else None)
    path = step_path_until_failure(events, test_id=primary)
    details = {}
    for event in events:
        if event.event_type != TestRunEventType.STEP_FAILED:
            continue
        tid = event.test_id or primary or "unknown"
        details[tid] = (event.message, _expected_from_message(event.message, event.step_id or ""))
    return path, details


def _test_log_path(run_id: str, test_id: str) -> Path:
    return artifacts_dir() / run_id / test_id / "test.log.json"


def _read_log_excerpt(run_id: str, test_id: str) -> tuple[int | None, str]:
    path = _test_log_path(run_id, test_id)
    if not path.is_file():
        return None, ""
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if len(text) > LOG_TAIL_CHARS:
        text = "…\n" + text[-LOG_TAIL_CHARS:]
    return len(raw), text


def _baseline_log_sizes(
    repo: SqlAlchemyRepository,
    *,
    scenario_id: str,
    test_id: str,
    exclude_run_id: str,
    n: int = LOG_BASELINE_N,
) -> list[int]:
    sizes: list[int] = []
    for run in repo.list_runs_for_scenario(scenario_id):
        if run.id == exclude_run_id:
            continue
        if run.status != "finished":
            continue
        events = repo.list_events(run.id)
        status, _ = test_outcome_from_events(events, test_id)
        if status != "finished":
            continue
        path = _test_log_path(run.id, test_id)
        if path.is_file():
            sizes.append(path.stat().st_size)
        if len(sizes) >= n:
            break
    return sizes


def _health_for_test(
    repo: SqlAlchemyRepository,
    *,
    scenario_id: str,
    run_id: str,
    test_id: str,
) -> tuple[list[HealthSignal], int | None, str]:
    size, excerpt = _read_log_excerpt(run_id, test_id)
    signals: list[HealthSignal] = []
    if size is None:
        signals.append(
            HealthSignal(
                test_id=test_id,
                kind="missing_log",
                severity="warn",
                message=f"Test log missing at {run_id}/{test_id}/test.log.json",
                current_bytes=None,
            )
        )
        return signals, size, excerpt
    if size == 0 or not excerpt.strip():
        signals.append(
            HealthSignal(
                test_id=test_id,
                kind="empty_log",
                severity="warn",
                message="Test log is empty — possible false positive / silent pass",
                current_bytes=size,
            )
        )
    baselines = _baseline_log_sizes(repo, scenario_id=scenario_id, test_id=test_id, exclude_run_id=run_id)
    if baselines and size is not None and size > 0:
        mid = float(median(baselines))
        if mid > 0:
            ratio = size / mid
            if ratio >= LOG_SIZE_RATIO_HIGH or ratio <= LOG_SIZE_RATIO_LOW:
                signals.append(
                    HealthSignal(
                        test_id=test_id,
                        kind="log_size_anomaly",
                        severity="warn",
                        message=(
                            f"Log size {size} B vs median {int(mid)} B "
                            f"over last {len(baselines)} passed run(s) (ratio {ratio:.2f})"
                        ),
                        current_bytes=size,
                        baseline_median_bytes=int(mid),
                    )
                )
    return signals, size, excerpt


def _fingerprint_occurrences_for_scenario(
    repo: SqlAlchemyRepository,
    scenario_id: str,
    *,
    fingerprint_filter: str | None = None,
    test_id_filter: str | None = None,
) -> tuple[list[FingerprintOccurrenceView], list[FlakinessSnapshot]]:
    scenario = repo.get_scenario(scenario_id)
    if scenario is None:
        raise LookupError("scenario not found")
    occurrence_rows = repo.list_fingerprint_occurrences(scenario_id)
    raw = [
        FingerprintOccurrenceView(
            run_id=row.run_id,
            test_id=row.test_id if row.test_id and row.test_id != "unknown" else _guess_test_id(scenario),
            step_id=row.step_id,
            sut_version=row.sut_version,
            framework_version=row.framework_version,
            fingerprint=row.fingerprint,
            label=row.label,
            message=row.message,
            created_at=row.created_at,
        )
        for row in occurrence_rows
    ]
    windowed = apply_occurrence_retention(
        raw,
        created_at_of=lambda r: r.created_at,
        run_id_of=lambda r: r.run_id,
        max_runs=scenario.history_max_runs,
        max_days=scenario.history_max_days,
    )
    if fingerprint_filter:
        windowed = [o for o in windowed if o.fingerprint == fingerprint_filter]
    if test_id_filter:
        windowed = [o for o in windowed if o.test_id == test_id_filter or o.test_id == "unknown"]
    flakiness = _flakiness_for_scenario(repo, scenario_id, scenario.test_ids_csv)
    return windowed, flakiness


def _run_test_ids(repo: SqlAlchemyRepository, run_id: str, scenario_test_ids: list[str]) -> list[str]:
    events = repo.list_events(run_id)
    seen: list[str] = []
    for event in events:
        tid = event.test_id
        if tid and tid != "unknown" and tid not in seen:
            seen.append(tid)
    if seen:
        # Keep scenario order when possible
        ordered = [t for t in scenario_test_ids if t in seen]
        ordered.extend(t for t in seen if t not in ordered)
        return ordered
    return list(scenario_test_ids)


def build_analysis_context(repo: SqlAlchemyRepository, request: AnalysisRequest) -> AnalysisContext:
    validate_analysis_request(request)

    if request.scope == AnalysisScope.TEST:
        assert request.run_id is not None and request.test_id is not None
        return _context_for_test(repo, request.run_id, request.test_id)

    if request.scope == AnalysisScope.RUN:
        assert request.run_id is not None
        # Run orchestration builds children separately; single-shot RUN context
        # is used only when analyzing without children (fallback).
        run = repo.get_run(request.run_id)
        if run is None:
            raise LookupError("run not found")
        scenario = repo.get_scenario(run.scenario_id)
        test_ids = _run_test_ids(
            repo,
            request.run_id,
            [t for t in (scenario.test_ids_csv.split(",") if scenario else []) if t],
        )
        return _context_for_tests(repo, request.run_id, test_ids, scope=AnalysisScope.RUN)

    assert request.scenario_id is not None
    scenario = repo.get_scenario(request.scenario_id)
    if scenario is None:
        raise LookupError("scenario not found")

    fingerprint_filter = request.fingerprint if request.scope == AnalysisScope.FINGERPRINT else None
    windowed, flakiness = _fingerprint_occurrences_for_scenario(
        repo,
        request.scenario_id,
        fingerprint_filter=fingerprint_filter,
    )

    # Per (run, test) When paths — avoid a single "primary test" path for the whole run
    step_paths: dict[str, list[str]] = {}
    failure_details: dict[str, tuple[str, str]] = {}
    for run_id, test_id in {(o.run_id, o.test_id) for o in windowed}:
        path, details = _load_run_step_meta(repo, run_id, test_id=test_id)
        step_paths[f"{run_id}::{test_id}"] = path
        if test_id in details:
            failure_details[run_id] = details[test_id]

    runs = repo.list_runs_for_scenario(request.scenario_id)
    latest = runs[0] if runs else None
    return AnalysisContext(
        request=request,
        scenario_name=scenario.name,
        sut_version=latest.sut_version if latest else scenario.sut_version,
        framework_version=latest.framework_version if latest else "unknown",
        occurrences=windowed,
        flakiness=flakiness,
        step_paths=step_paths,
        failure_details=failure_details,
    )


def _context_for_test(repo: SqlAlchemyRepository, run_id: str, test_id: str) -> AnalysisContext:
    """TEST scope: evidence from this run + this test only (not scenario history)."""
    run = repo.get_run(run_id)
    if run is None:
        raise LookupError("run not found")
    scenario = repo.get_scenario(run.scenario_id)
    events = repo.list_events(run_id)
    step_messages: list[tuple[str, str, str]] = []
    run_fps: list[FingerprintOccurrenceView] = []
    for event in events:
        if event.event_type != TestRunEventType.STEP_FAILED:
            continue
        tid = event.test_id or "unknown"
        if tid != test_id:
            continue
        step_id = event.step_id or "unknown"
        digest, label = error_fingerprint(step_id, event.error_trace, event.message)
        step_messages.append((test_id, step_id, event.message))
        run_fps.append(
            FingerprintOccurrenceView(
                run_id=run_id,
                test_id=test_id,
                step_id=step_id,
                sut_version=run.sut_version,
                framework_version=run.framework_version,
                fingerprint=digest,
                label=label,
                message=event.message,
                created_at=event.timestamp,
            )
        )

    path, details = _load_run_step_meta(repo, run_id, test_id=test_id)
    health, _size, excerpt = _health_for_test(
        repo, scenario_id=run.scenario_id, run_id=run_id, test_id=test_id
    )
    log_excerpts = {test_id: excerpt} if excerpt else {}

    return AnalysisContext(
        request=AnalysisRequest(
            scope=AnalysisScope.TEST,
            scenario_id=run.scenario_id,
            run_id=run_id,
            test_id=test_id,
        ),
        scenario_name=scenario.name if scenario else "",
        sut_version=run.sut_version,
        framework_version=run.framework_version,
        occurrences=run_fps,
        flakiness=[],
        run_step_messages=step_messages,
        step_paths={run_id: path},
        test_step_paths={test_id: path},
        failure_details={run_id: details.get(test_id, ("", ""))},
        log_excerpts=log_excerpts,
        health_signals=health,
    )


def _context_for_tests(
    repo: SqlAlchemyRepository,
    run_id: str,
    test_ids: list[str],
    *,
    scope: AnalysisScope,
) -> AnalysisContext:
    """RUN scope: evidence from this run only (not scenario history)."""
    run = repo.get_run(run_id)
    if run is None:
        raise LookupError("run not found")
    scenario = repo.get_scenario(run.scenario_id)
    events = repo.list_events(run_id)
    step_messages: list[tuple[str, str, str]] = []
    run_fps: list[FingerprintOccurrenceView] = []
    for event in events:
        if event.event_type != TestRunEventType.STEP_FAILED:
            continue
        step_id = event.step_id or "unknown"
        test_id = event.test_id or "unknown"
        if test_id == "unknown":
            continue
        digest, label = error_fingerprint(step_id, event.error_trace, event.message)
        step_messages.append((test_id, step_id, event.message))
        run_fps.append(
            FingerprintOccurrenceView(
                run_id=run_id,
                test_id=test_id,
                step_id=step_id,
                sut_version=run.sut_version,
                framework_version=run.framework_version,
                fingerprint=digest,
                label=label,
                message=event.message,
                created_at=event.timestamp,
            )
        )

    health: list[HealthSignal] = []
    log_excerpts: dict[str, str] = {}
    test_step_paths: dict[str, list[str]] = {}
    for test_id in test_ids:
        signals, _size, excerpt = _health_for_test(
            repo, scenario_id=run.scenario_id, run_id=run_id, test_id=test_id
        )
        health.extend(signals)
        if excerpt:
            log_excerpts[test_id] = excerpt
        path, _details = _load_run_step_meta(repo, run_id, test_id=test_id)
        test_step_paths[test_id] = path

    return AnalysisContext(
        request=AnalysisRequest(scope=scope, scenario_id=run.scenario_id, run_id=run_id),
        scenario_name=scenario.name if scenario else "",
        sut_version=run.sut_version,
        framework_version=run.framework_version,
        occurrences=run_fps,
        flakiness=[],
        run_step_messages=step_messages,
        step_paths={},
        test_step_paths=test_step_paths,
        failure_details={},
        log_excerpts=log_excerpts,
        health_signals=health,
    )


def _guess_test_id(scenario) -> str:
    ids = [t for t in scenario.test_ids_csv.split(",") if t]
    return ids[0] if len(ids) == 1 else "unknown"


def _flakiness_for_scenario(
    repo: SqlAlchemyRepository,
    scenario_id: str,
    test_ids_csv: str,
) -> list[FlakinessSnapshot]:
    test_ids = [t for t in test_ids_csv.split(",") if t]
    runs = repo.list_runs_for_scenario(scenario_id)
    buckets: dict[tuple[str, str, str], list[tuple[str, int | None]]] = {}
    for run in runs:
        events = repo.list_events(run.id)
        for test_id in test_ids:
            status, duration = test_outcome_from_events(events, test_id)
            if status is None:
                if run.status in {"finished", "failed"} and len(test_ids) == 1:
                    status = run.status
                    duration = run.duration_ms
                else:
                    continue
            key = (test_id, run.sut_version, run.framework_version)
            buckets.setdefault(key, []).append((status, duration))

    snapshots: list[FlakinessSnapshot] = []
    for (test_id, sut, fw), samples in buckets.items():
        stats = compute_flakiness(
            samples,
            test_id=test_id,
            sut_version=sut,
            framework_version=fw,
        )
        snapshots.append(
            FlakinessSnapshot(
                test_id=stats.test_id,
                sut_version=stats.sut_version,
                framework_version=stats.framework_version,
                total_runs=stats.total_runs,
                failed_runs=stats.failed_runs,
                fail_rate=stats.fail_rate,
                reliability=stats.reliability,
            )
        )
    return snapshots


class HeuristicFailureAnalyzer:
    """Deterministic structured report — used in tests and when no LLM key is set."""

    def analyze(self, context: AnalysisContext) -> AnalysisReport:
        errors = _errors_from_occurrences(context)
        # Current-run failures without fingerprint rows still surface via step messages
        if (
            context.request.scope in {AnalysisScope.RUN, AnalysisScope.TEST}
            and not errors
            and context.run_step_messages
        ):
            for test_id, step_id, message in context.run_step_messages:
                run_id = context.request.run_id or ""
                path = context.test_step_paths.get(test_id) or [step_id]
                digest, label = error_fingerprint(step_id, None, message)
                errors.append(
                    _build_error_item(
                        context,
                        fingerprint=digest,
                        label=label or message or "step failed",
                        message=message,
                        where=[FailureWhere(test_id=test_id, step_id=step_id)],
                        occurrence_count=1,
                        last_run_id=run_id,
                        when_steps=path,
                    )
                )

        # Run/test scopes never attach history flakiness — that belongs to scenario/history analyze
        flakiness = (
            []
            if context.request.scope in {AnalysisScope.RUN, AnalysisScope.TEST}
            else context.flakiness
        )

        summary = _summary(context.request.scope, errors, flakiness, context.health_signals)
        if context.request.scope in {AnalysisScope.RUN, AnalysisScope.TEST}:
            outcome = _run_outcome(errors, context.health_signals)
            summary = f"Run outcome: {outcome}. {summary}"
            scenario_rel = outcome
        else:
            scenario_rel = _scenario_reliability(flakiness)
            if scenario_rel != "unknown":
                summary = f"Scenario reliability: {scenario_rel}. {summary}"
        return AnalysisReport(
            id=str(uuid.uuid4()),
            scope=context.request.scope,
            scenario_id=context.request.scenario_id,
            scenario_name=context.scenario_name,
            run_id=context.request.run_id,
            test_id=context.request.test_id,
            fingerprint=context.request.fingerprint,
            sut_version=context.sut_version,
            framework_version=context.framework_version,
            infra=context.infra,
            summary=summary,
            scenario_reliability=scenario_rel,
            errors=errors,
            flakiness=flakiness,
            health_signals=context.health_signals,
            generated_at=datetime.now(UTC),
            contracts_version=CONTRACTS_VERSION,
        )


def _errors_from_occurrences(context: AnalysisContext) -> list[ErrorAnalysisItem]:
    by_family: dict[str, list[FingerprintOccurrenceView]] = defaultdict(list)
    for occ in context.occurrences:
        family = normalize_error_message(occ.message) or occ.fingerprint
        by_family[family].append(occ)

    errors: list[ErrorAnalysisItem] = []
    for _family, rows in by_family.items():
        rows_sorted = sorted(rows, key=lambda r: r.created_at, reverse=True)
        latest = rows_sorted[0]
        where_keys = {(r.test_id, r.step_id) for r in rows}
        where = [FailureWhere(test_id=t, step_id=s) for t, s in sorted(where_keys)]
        when_steps = (
            context.test_step_paths.get(latest.test_id)
            or context.step_paths.get(f"{latest.run_id}::{latest.test_id}")
            or context.step_paths.get(latest.run_id)
            or [latest.step_id]
        )
        errors.append(
            _build_error_item(
                context,
                fingerprint=latest.fingerprint,
                label=latest.label,
                message=latest.message or latest.label,
                where=where,
                occurrence_count=len(rows),
                last_run_id=latest.run_id,
                when_steps=when_steps,
                sut_versions=sorted({r.sut_version for r in rows}),
                framework_versions=sorted({r.framework_version for r in rows}),
            )
        )
    errors.sort(key=lambda e: e.occurrence_count, reverse=True)
    return errors


def _build_error_item(
    context: AnalysisContext,
    *,
    fingerprint: str,
    label: str,
    message: str,
    where: list[FailureWhere],
    occurrence_count: int,
    last_run_id: str,
    when_steps: list[str],
    sut_versions: list[str] | None = None,
    framework_versions: list[str] | None = None,
) -> ErrorAnalysisItem:
    tests = sorted({w.test_id for w in where})
    primary_test = tests[0] if tests else "unknown"
    then_actual = message or label or "Step failed"
    expected = _expected_from_message(message, when_steps[-1] if when_steps else "")
    error_type, root_cause, confidence, likely_sut, components = _classify(message, primary_test)
    log_hint = ""
    if primary_test in context.log_excerpts:
        log_hint = f" · log excerpt available ({len(context.log_excerpts[primary_test])} chars)"
    given = (
        f"Scenario '{context.scenario_name or context.request.scenario_id or '—'}' · "
        f"infra {context.infra} · SUT {context.sut_version} · FW {context.framework_version} · "
        f"test {primary_test}{log_hint}"
    )
    description = (
        f"{label or message or 'Failure'} in test(s) [{', '.join(tests)}] "
        f"via steps [{' → '.join(when_steps)}]"
    )
    return ErrorAnalysisItem(
        fingerprint=fingerprint,
        label=label,
        description=description,
        where=where,
        occurrence_count=occurrence_count,
        last_failure_run_id=last_run_id or None,
        sut_versions=sut_versions or [context.sut_version],
        framework_versions=framework_versions or [context.framework_version],
        given=given,
        when_steps=when_steps,
        then_actual=then_actual,
        expected=expected,
        root_cause_name=root_cause,
        confidence_pct=confidence,
        error_type=error_type,
        components=components,
        reproduce_path=(
            f"Open last failure run {last_run_id}; replay When path: {' → '.join(when_steps)}"
        ),
        likely_sut_issue=likely_sut,
        recommended_actions=_actions_for(error_type, message),
    )


def _expected_from_message(message: str, step_id: str) -> str:
    text = message.lower()
    if "tails" in text or "coin" in text:
        return "coin_flip succeeds (heads) — step status success"
    if "timeout" in text:
        return f"{step_id or 'step'} completes within timeout with HTTP success"
    if step_id:
        return f"step '{step_id}' succeeds"
    return "step succeeds"


def _classify(message: str, test_id: str) -> tuple[str, str, int, bool, list[str]]:
    text = message.lower()
    if "tails" in text or "simulated flake" in text or test_id == "flaky_coin":
        return (
            "flake",
            "intentional test flake (simulated coin)",
            90,
            False,
            ["test", "step"],
        )
    if any(t in text for t in ("timeout", "502", "503", "connection", "5xx")):
        return ("timeout", "SUT/infra latency or availability", 70, True, ["SUT", "infra", "step"])
    if "assert" in text or "mismatch" in text or "expected" in text:
        return ("assertion", "assertion / expectation mismatch", 65, False, ["test", "step", "SUT"])
    return ("unknown", "unclassified step failure", 40, False, ["test", "step"])


def _actions_for(error_type: str, message: str) -> list[str]:
    if error_type == "flake":
        return [
            "Treat as known flaky demo unless fail_rate exceeds team threshold",
            "Use fingerprint timeline to confirm pattern is random vs regression",
        ]
    if error_type == "timeout":
        return [
            "Inspect SUT health / latency around the failure timestamp",
            "Confirm the failure is not an environment flake before changing the test",
        ]
    return [
        "Compare Then vs Expected for the failing step",
        "Inspect step logs and artifacts on the last failure run",
    ]


def _run_outcome(errors: list[ErrorAnalysisItem], health: list[HealthSignal]) -> str:
    """Single-run / single-test verdict — not history flakiness."""
    if errors:
        return "failed"
    if any(signal.severity == "warn" for signal in health):
        return "watch"
    return "passed"


def _scenario_reliability(flakiness: list[FlakinessSnapshot]) -> str:
    """Worst bucket wins — scenario is only as stable as its flakiest (test, SUT, FW) slice."""
    if not flakiness:
        return "unknown"
    return reliability_label(max(item.fail_rate for item in flakiness))


def _summary(
    scope: AnalysisScope,
    errors: list[ErrorAnalysisItem],
    flakiness: list[FlakinessSnapshot],
    health: list[HealthSignal],
) -> str:
    parts: list[str] = []
    if errors:
        parts.append(f"{len(errors)} distinct error(s) in {scope.value} scope.")
        shared = [e for e in errors if len({(w.test_id) for w in e.where}) > 1]
        if shared:
            parts.append(f"{len(shared)} error(s) span multiple tests.")
    else:
        parts.append(f"No step failures in {scope.value} scope.")
    if health:
        parts.append(f"{len(health)} log health signal(s) (missing/empty/size drift).")
    flaky = [f for f in flakiness if f.fail_rate > 0.1]
    if flaky:
        parts.append(f"{len(flaky)} test(s) above 10% fail rate in history.")
    return " ".join(parts)


def _analyze_and_save(
    repo: SqlAlchemyRepository,
    request: AnalysisRequest,
    analyzer: FailureAnalyzer,
    *,
    parent_analysis_id: str | None = None,
) -> AnalysisReport:
    context = build_analysis_context(repo, request)
    report = analyzer.analyze(context)
    if parent_analysis_id:
        report = report.model_copy(update={"parent_analysis_id": parent_analysis_id})
    repo.save_analysis_report(report)
    return report


def _analyze_run_with_tests(
    repo: SqlAlchemyRepository,
    request: AnalysisRequest,
    analyzer: FailureAnalyzer,
) -> AnalysisReport:
    assert request.run_id is not None
    run = repo.get_run(request.run_id)
    if run is None:
        raise LookupError("run not found")
    scenario = repo.get_scenario(run.scenario_id)
    scenario_ids = [t for t in (scenario.test_ids_csv.split(",") if scenario else []) if t]
    test_ids = _run_test_ids(repo, request.run_id, scenario_ids)
    parent_id = str(uuid.uuid4())

    # Sequential per-test analyses (one report each), then roll up.
    # Parallel LLM workers can be added later; SQLite + threads is unsafe here.
    child_reports = [
        _analyze_and_save(
            repo,
            AnalysisRequest(
                scope=AnalysisScope.TEST,
                scenario_id=run.scenario_id,
                run_id=request.run_id,
                test_id=test_id,
            ),
            analyzer,
            parent_analysis_id=parent_id,
        )
        for test_id in test_ids
    ]

    combined_ctx = _context_for_tests(repo, request.run_id, test_ids, scope=AnalysisScope.RUN)
    combined = analyzer.analyze(combined_ctx)
    refs = [
        TestAnalysisRef(
            test_id=c.test_id or "",
            analysis_id=c.id,
            summary=c.summary,
            health_signal_count=len(c.health_signals),
            error_count=len(c.errors),
        )
        for c in child_reports
        if c.test_id
    ]
    all_errors = list(combined.errors)
    seen_fp = {e.fingerprint for e in all_errors}
    for child in child_reports:
        for err in child.errors:
            if err.fingerprint not in seen_fp:
                all_errors.append(err)
                seen_fp.add(err.fingerprint)
    all_health = list(combined.health_signals)
    outcome = _run_outcome(all_errors, all_health)
    roll_up = _run_roll_up_summary(child_reports, all_errors, all_health)
    roll_up = f"Run outcome: {outcome}. {roll_up}"
    report = combined.model_copy(
        update={
            "id": parent_id,
            "scope": AnalysisScope.RUN,
            "scenario_id": run.scenario_id,
            "run_id": request.run_id,
            "errors": all_errors,
            "health_signals": all_health,
            "test_analyses": refs,
            "scenario_reliability": outcome,
            "summary": roll_up,
        }
    )
    repo.save_analysis_report(report)
    return report


def _run_roll_up_summary(
    children: list[AnalysisReport],
    errors: list[ErrorAnalysisItem],
    health: list[HealthSignal],
) -> str:
    parts = [
        f"Analyzed {len(children)} test(s).",
        f"{len(errors)} distinct error family(ies).",
    ]
    if health:
        parts.append(f"{len(health)} log health signal(s).")
    failed_tests = [c.test_id for c in children if c.errors]
    if failed_tests:
        parts.append(f"Tests with errors: {', '.join(t for t in failed_tests if t)}.")
    return " ".join(parts)


def run_analysis(
    repo: SqlAlchemyRepository,
    request: AnalysisRequest,
    analyzer: FailureAnalyzer,
) -> AnalysisReport:
    if request.scope == AnalysisScope.RUN:
        return _analyze_run_with_tests(repo, request, analyzer)
    return _analyze_and_save(repo, request, analyzer)
