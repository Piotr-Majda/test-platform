"""Duration trends, step rollup, fingerprints — Given / When / Then."""

from datetime import UTC, datetime

from test_platform_contracts import StepStatus, TestRunEvent, TestRunEventType

from test_platform_api.history import (
    collect_fingerprints,
    compute_duration_trend,
    compute_flakiness,
    compute_step_history,
    error_fingerprint,
    reliability_label,
)


def test_duration_trend_faster_when_last_below_previous_avg() -> None:
    trend = compute_duration_trend([80, 120, 130, 140])
    assert trend.direction == "faster"
    assert trend.last_duration_ms == 80
    assert trend.previous_avg_ms == 130.0
    assert trend.delta_ms == -50


def test_duration_trend_slower_when_last_above_previous_avg() -> None:
    trend = compute_duration_trend([200, 100, 90])
    assert trend.direction == "slower"
    assert trend.delta_ms == 105


def test_reliability_stable_only_for_low_fail_rate() -> None:
    assert reliability_label(0.0) == "stable"
    assert reliability_label(0.1) == "stable"
    assert reliability_label(0.2) == "watch"
    assert reliability_label(0.5) == "flaky"


def test_flakiness_includes_trend_newest_first() -> None:
    stats = compute_flakiness(
        [("finished", 50), ("finished", 100), ("finished", 110)],
        test_id="google_title",
        sut_version="1.0.0",
        framework_version="0.1.0",
    )
    assert stats.trend.direction == "faster"
    assert stats.trend.last_duration_ms == 50
    assert stats.reliability == "stable"


def test_high_fail_rate_is_flaky_not_stable() -> None:
    stats = compute_flakiness(
        [("failed", 10), ("finished", 10)],
        test_id="flaky_coin",
        sut_version="1.0.0",
        framework_version="0.1.0",
    )
    assert stats.fail_rate == 0.5
    assert stats.reliability == "flaky"


def test_step_history_rollup() -> None:
    rows = compute_step_history(
        {
            "coin_flip": [("failed", 2), ("finished", 3), ("failed", 2)],
            "open_page": [("finished", 100), ("finished", 90)],
        }
    )
    by_id = {r.step_id: r for r in rows}
    assert by_id["coin_flip"].failed == 2
    assert by_id["coin_flip"].total == 3
    assert abs(by_id["coin_flip"].fail_rate - (2 / 3)) < 0.001


def test_error_fingerprint_stable_for_same_failure() -> None:
    a, label_a = error_fingerprint(
        "coin_flip",
        "StepFailedError: coin landed on tails (simulated flake)\n",
        "coin landed on tails (simulated flake)",
    )
    b, label_b = error_fingerprint(
        "coin_flip",
        "Traceback...\nStepFailedError: coin landed on tails (simulated flake)\n",
        "coin landed on tails (simulated flake)",
    )
    assert a == b
    assert "coin_flip" in label_a
    assert label_a == label_b


def test_fingerprint_groups_keep_last_10_occurrences() -> None:
    now = datetime.now(UTC)
    failures = []
    for i in range(12):
        event = TestRunEvent(
            run_id=f"run-{i}",
            event_type=TestRunEventType.STEP_FAILED,
            test_id="flaky_coin",
            step_id="coin_flip",
            status=StepStatus.FAILED,
            message="coin landed on tails (simulated flake)",
            error_trace="StepFailedError: coin landed on tails (simulated flake)",
            timestamp=now,
        )
        failures.append(("1.0.0", "0.1.0", "flaky_coin", "coin_flip", event, now))

    groups = collect_fingerprints(failures)
    assert len(groups) == 1
    assert groups[0].count == 12
    assert len(groups[0].recent_failures) == 10
    assert groups[0].recent_failures[0].run_id == "run-0"
