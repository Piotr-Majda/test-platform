"""History projections and flakiness — no duplicated run storage."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from test_platform_contracts import TestRunEvent, TestRunEventType

_TREND_STABLE_MS = 25
_RECENT_FAILURE_LIMIT = 10
# Reliability: "stable" means low flakiness, not "duration unchanged"
_RELIABILITY_STABLE_MAX = 0.10
_RELIABILITY_WATCH_MAX = 0.30

T = TypeVar("T")


@dataclass(frozen=True)
class FlakinessKey:
    test_id: str
    sut_version: str
    framework_version: str


@dataclass
class DurationTrend:
    last_duration_ms: int | None
    previous_avg_ms: float | None
    delta_ms: int | None
    direction: str  # faster | slower | stable | unknown


@dataclass
class FlakinessStats:
    test_id: str
    sut_version: str
    framework_version: str
    total_runs: int
    failed_runs: int
    fail_rate: float
    avg_duration_ms: float | None
    min_duration_ms: int | None
    max_duration_ms: int | None
    trend: DurationTrend = field(
        default_factory=lambda: DurationTrend(None, None, None, "unknown")
    )
    reliability: str = "unknown"


@dataclass
class StepHistoryStats:
    step_id: str
    total: int
    failed: int
    fail_rate: float
    avg_duration_ms: float | None
    trend: DurationTrend
    reliability: str = "unknown"


@dataclass
class FailureOccurrence:
    run_id: str
    test_id: str
    step_id: str
    message: str
    created_at: datetime


@dataclass
class FingerprintGroup:
    fingerprint: str
    label: str
    step_id: str
    test_id: str
    sut_version: str
    framework_version: str
    count: int
    recent_failures: list[FailureOccurrence]
    occurrences: list[FailureOccurrence] = field(default_factory=list)


def test_outcome_from_events(events: list[TestRunEvent], test_id: str) -> tuple[str | None, int | None]:
    """Return (status, duration_ms) for a test_id from run events."""
    status: str | None = None
    duration: int | None = None
    for event in events:
        if event.test_id != test_id:
            continue
        if event.event_type == TestRunEventType.TEST_FINISHED:
            status = "finished"
            duration = event.duration_ms
        elif event.event_type == TestRunEventType.TEST_FAILED:
            status = "failed"
            duration = event.duration_ms
    return status, duration


def scenario_duration_from_events(events: list[TestRunEvent]) -> int | None:
    """Prefer explicit run total; otherwise sum test action durations."""
    for event in reversed(events):
        if event.event_type in {
            TestRunEventType.RUN_FINISHED,
            TestRunEventType.RUN_FAILED,
        }:
            if event.duration_ms is not None:
                return event.duration_ms
            break
    totals = [
        event.duration_ms
        for event in events
        if event.event_type
        in {TestRunEventType.TEST_FINISHED, TestRunEventType.TEST_FAILED}
        and event.duration_ms is not None
    ]
    return sum(totals) if totals else None


def normalize_error_message(message: str) -> str:
    text = re.sub(r"\s+", " ", message.strip().lower())
    text = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "<id>",
        text,
    )
    text = re.sub(r"\b\d+\b", "N", text)
    return text[:200]


def exception_type_from_failure(error_trace: str | None, message: str) -> str:
    if error_trace:
        for line in reversed(error_trace.strip().splitlines()):
            stripped = line.strip()
            if not stripped or stripped.startswith("File ") or stripped.startswith("Traceback"):
                continue
            if ":" in stripped and not stripped.startswith("^"):
                name = stripped.split(":", 1)[0].strip().split(".")[-1]
                if name and " " not in name:
                    return name
    return "Error"


def error_fingerprint(step_id: str, error_trace: str | None, message: str) -> tuple[str, str]:
    """Return (fingerprint_id, human label) for a step failure."""
    exc_type = exception_type_from_failure(error_trace, message)
    normalized = normalize_error_message(message)
    raw = f"{step_id}|{exc_type}|{normalized}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    label = f"{step_id}: {exc_type}: {message.strip()[:80]}"
    return digest, label


def compute_duration_trend(durations_newest_first: list[int | None]) -> DurationTrend:
    """Compare newest duration to the average of previous samples."""
    present = [d for d in durations_newest_first if d is not None]
    if not present:
        return DurationTrend(None, None, None, "unknown")
    last = present[0]
    previous = present[1:]
    if not previous:
        return DurationTrend(last, None, None, "unknown")
    previous_avg = sum(previous) / len(previous)
    delta = int(round(last - previous_avg))
    if abs(delta) <= _TREND_STABLE_MS:
        direction = "steady"
    elif delta < 0:
        direction = "faster"
    else:
        direction = "slower"
    return DurationTrend(last, previous_avg, delta, direction)


def reliability_label(fail_rate: float) -> str:
    """stable ≤10% fail rate; watch ≤30%; otherwise flaky."""
    if fail_rate <= _RELIABILITY_STABLE_MAX:
        return "stable"
    if fail_rate <= _RELIABILITY_WATCH_MAX:
        return "watch"
    return "flaky"


def compute_flakiness(
    samples: list[tuple[str, int | None]],
    *,
    test_id: str,
    sut_version: str,
    framework_version: str,
) -> FlakinessStats:
    """samples: newest-first list of (status, duration_ms) for the flakiness key."""
    total = len(samples)
    failed = sum(1 for status, _ in samples if status == "failed")
    fail_rate = (failed / total) if total else 0.0
    durations = [d for _, d in samples if d is not None]
    avg = (sum(durations) / len(durations)) if durations else None
    return FlakinessStats(
        test_id=test_id,
        sut_version=sut_version,
        framework_version=framework_version,
        total_runs=total,
        failed_runs=failed,
        fail_rate=fail_rate,
        avg_duration_ms=avg,
        min_duration_ms=min(durations) if durations else None,
        max_duration_ms=max(durations) if durations else None,
        trend=compute_duration_trend([d for _, d in samples]),
        reliability=reliability_label(fail_rate),
    )


def compute_step_history(
    step_samples: dict[str, list[tuple[str, int | None]]],
) -> list[StepHistoryStats]:
    """step_samples: step_id -> newest-first (status, duration_ms)."""
    rows: list[StepHistoryStats] = []
    for step_id, samples in sorted(step_samples.items()):
        total = len(samples)
        failed = sum(1 for status, _ in samples if status == "failed")
        fail_rate = (failed / total) if total else 0.0
        durations = [d for _, d in samples if d is not None]
        avg = (sum(durations) / len(durations)) if durations else None
        rows.append(
            StepHistoryStats(
                step_id=step_id,
                total=total,
                failed=failed,
                fail_rate=fail_rate,
                avg_duration_ms=avg,
                trend=compute_duration_trend([d for _, d in samples]),
                reliability=reliability_label(fail_rate),
            )
        )
    return rows


def collect_fingerprints(
    failures: list[tuple[str, str, str, str, TestRunEvent, datetime]],
) -> list[FingerprintGroup]:
    """failures: (sut, fw, test_id, step_id, event, created_at) newest-first preferred."""
    rows: list[tuple[str, str, str, str, str, str, str, str, datetime]] = []
    for sut, fw, test_id, step_id, event, created_at in failures:
        digest, label = error_fingerprint(step_id, event.error_trace, event.message)
        rows.append(
            (
                event.run_id,
                test_id,
                step_id,
                sut,
                fw,
                digest,
                label,
                event.message,
                created_at,
            )
        )
    return group_fingerprint_rows(rows)


def group_fingerprint_rows(
    rows: list[tuple[str, str, str, str, str, str, str, str, datetime]],
) -> list[FingerprintGroup]:
    """rows: (run_id, test_id, step_id, sut, fw, fingerprint, label, message, created_at) newest-first."""
    buckets: dict[tuple[str, str, str, str, str], FingerprintGroup] = {}
    for run_id, test_id, step_id, sut, fw, digest, label, message, created_at in rows:
        key = (digest, sut, fw, test_id, step_id)
        occurrence = FailureOccurrence(
            run_id=run_id,
            test_id=test_id,
            step_id=step_id,
            message=message,
            created_at=created_at,
        )
        group = buckets.get(key)
        if group is None:
            buckets[key] = FingerprintGroup(
                fingerprint=digest,
                label=label,
                step_id=step_id,
                test_id=test_id,
                sut_version=sut,
                framework_version=fw,
                count=1,
                recent_failures=[occurrence],
                occurrences=[occurrence],
            )
        else:
            group.count += 1
            group.occurrences.append(occurrence)
            if len(group.recent_failures) < _RECENT_FAILURE_LIMIT:
                group.recent_failures.append(occurrence)
    return sorted(buckets.values(), key=lambda g: (-g.count, g.label))


def apply_occurrence_retention(
    rows: list[T],
    *,
    created_at_of: Callable[[T], datetime],
    run_id_of: Callable[[T], str],
    max_runs: int | None,
    max_days: int | None,
    now: datetime | None = None,
) -> list[T]:
    """Same retention idea as run history: max_days ∩ last max_runs (by distinct run_id)."""
    now = now or datetime.now(UTC)
    filtered = list(rows)
    if max_days is not None:
        cutoff = now - timedelta(days=max_days)
        kept: list[T] = []
        for row in filtered:
            created = created_at_of(row)
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if created >= cutoff:
                kept.append(row)
        filtered = kept

    if max_runs is None:
        return filtered

    # rows expected newest-first; collect newest distinct run ids
    allowed_runs: list[str] = []
    for row in filtered:
        run_id = run_id_of(row)
        if run_id not in allowed_runs:
            allowed_runs.append(run_id)
        if len(allowed_runs) >= max_runs:
            break
    allowed = set(allowed_runs)
    return [row for row in filtered if run_id_of(row) in allowed]
