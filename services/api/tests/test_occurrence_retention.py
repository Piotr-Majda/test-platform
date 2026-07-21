"""Fingerprint timeline retention matches history config — Given / When / Then."""

from datetime import UTC, datetime, timedelta

from test_platform_api.history import apply_occurrence_retention


def test_occurrence_retention_keeps_last_max_runs() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    rows = [
        ("r3", now - timedelta(hours=1)),
        ("r2", now - timedelta(hours=2)),
        ("r2", now - timedelta(hours=3)),
        ("r1", now - timedelta(hours=4)),
    ]

    kept = apply_occurrence_retention(
        rows,
        created_at_of=lambda r: r[1],
        run_id_of=lambda r: r[0],
        max_runs=2,
        max_days=None,
        now=now,
    )

    assert [r[0] for r in kept] == ["r3", "r2", "r2"]


def test_occurrence_retention_applies_max_days() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    rows = [
        ("r2", now - timedelta(days=1)),
        ("r1", now - timedelta(days=10)),
    ]

    kept = apply_occurrence_retention(
        rows,
        created_at_of=lambda r: r[1],
        run_id_of=lambda r: r[0],
        max_runs=50,
        max_days=3,
        now=now,
    )

    assert [r[0] for r in kept] == ["r2"]
