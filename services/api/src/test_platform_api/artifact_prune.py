"""Prune on-disk run artifacts using scenario artifact retention settings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from test_platform_api.artifact_storage import artifact_storage
from test_platform_api.db import RunRow, SqlAlchemyRepository


def prune_scenario_artifacts(
    repo: SqlAlchemyRepository,
    scenario_id: str,
    *,
    max_runs: int | None,
    max_days: int | None,
    keep_at_least_one_failed: bool,
    history_max_runs: int | None,
    history_max_days: int | None,
    now: datetime | None = None,
) -> int:
    """
    Delete artifact directories for runs that fall outside retention.
    Returns number of run directories removed.
    """
    now = now or datetime.now(UTC)
    runs = repo.list_runs_for_scenario(scenario_id)
    keep_ids = _runs_to_keep(
        runs,
        max_runs=max_runs,
        max_days=max_days,
        keep_at_least_one_failed=keep_at_least_one_failed,
        history_max_runs=history_max_runs,
        history_max_days=history_max_days,
        now=now,
    )
    storage = artifact_storage()
    deleted = 0
    for run in runs:
        if run.id in keep_ids:
            continue
        deleted += storage.delete_prefix(run.id)
    return deleted


def _runs_in_window(
    runs: list[RunRow],
    *,
    max_runs: int | None,
    max_days: int | None,
    now: datetime,
) -> list[RunRow]:
    """Filter newest-first runs by max_days ∩ max_runs."""
    candidates = list(runs)
    if max_days is not None:
        cutoff = now - timedelta(days=max_days)
        kept: list[RunRow] = []
        for run in candidates:
            created = run.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if created >= cutoff:
                kept.append(run)
        candidates = kept

    if max_runs is not None and len(candidates) > max_runs:
        candidates = candidates[:max_runs]
    return candidates


def _runs_to_keep(
    runs: list[RunRow],
    *,
    max_runs: int | None,
    max_days: int | None,
    keep_at_least_one_failed: bool,
    history_max_runs: int | None,
    history_max_days: int | None,
    now: datetime,
) -> set[str]:
    artifact_window = _runs_in_window(runs, max_runs=max_runs, max_days=max_days, now=now)
    keep = {r.id for r in artifact_window}

    if not keep_at_least_one_failed:
        return keep

    history_window = _runs_in_window(
        runs,
        max_runs=history_max_runs,
        max_days=history_max_days,
        now=now,
    )
    if any(r.status == "failed" and r.id in keep for r in history_window):
        return keep

    for run in history_window:
        if run.status == "failed":
            keep.add(run.id)
            break
    return keep
