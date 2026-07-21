from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import uuid

from test_platform_api.artifact_prune import prune_scenario_artifacts
from test_platform_api.db import SqlAlchemyRepository, create_session_factory
from test_platform_api.paths import artifacts_dir

_ROOT = Path(__file__).resolve().parent / "_tmp_artifact_prune"


def _repo(monkeypatch) -> tuple[SqlAlchemyRepository, Path]:
    case_dir = _ROOT / uuid.uuid4().hex
    case_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARTIFACTS_DIR", str(case_dir / "artifacts"))
    factory = create_session_factory("sqlite:///:memory:")
    return SqlAlchemyRepository(factory()), case_dir


def _touch_run_dir(run_id: str) -> Path:
    run_dir = artifacts_dir() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "note.txt").write_text("keep-or-drop", encoding="utf-8")
    return run_dir


def _make_run(
    repo: SqlAlchemyRepository,
    run_id: str,
    *,
    status: str,
    created_at: datetime,
) -> None:
    repo.create_run(run_id, "s1", sut_version="1.0.0", framework_version="0.1.0")
    repo.update_run_status(run_id, status)
    row = repo.get_run(run_id)
    assert row is not None
    row.created_at = created_at
    repo._session.flush()
    _touch_run_dir(run_id)


def test_prune_keeps_only_max_artifact_runs(monkeypatch) -> None:
    repo, case_dir = _repo(monkeypatch)
    try:
        repo.create_scenario("s1", "S", ["t1"], artifact_max_runs=2)
        now = datetime.now(UTC)
        for offset, run_id in enumerate(["r1", "r2", "r3"]):
            _make_run(repo, run_id, status="finished", created_at=now + timedelta(seconds=offset))

        deleted = prune_scenario_artifacts(
            repo,
            "s1",
            max_runs=2,
            max_days=None,
            keep_at_least_one_failed=False,
            history_max_runs=30,
            history_max_days=None,
        )

        assert deleted == 1
        assert not (artifacts_dir() / "r1").exists()
        assert (artifacts_dir() / "r2").exists()
        assert (artifacts_dir() / "r3").exists()
    finally:
        repo._session.close()
        shutil.rmtree(case_dir, ignore_errors=True)


def test_prune_keeps_older_failed_inside_history_window(monkeypatch) -> None:
    """History 30 / artifacts 2: keep last 2 plus one failed still in history."""
    repo, case_dir = _repo(monkeypatch)
    try:
        repo.create_scenario("s1", "S", ["t1"])
        now = datetime.now(UTC)
        # oldest → newest: fail, pass, pass, pass
        _make_run(repo, "fail-old", status="failed", created_at=now + timedelta(seconds=0))
        _make_run(repo, "p1", status="finished", created_at=now + timedelta(seconds=1))
        _make_run(repo, "p2", status="finished", created_at=now + timedelta(seconds=2))
        _make_run(repo, "p3", status="finished", created_at=now + timedelta(seconds=3))

        deleted = prune_scenario_artifacts(
            repo,
            "s1",
            max_runs=2,
            max_days=None,
            keep_at_least_one_failed=True,
            history_max_runs=30,
            history_max_days=None,
        )

        assert deleted == 1
        assert (artifacts_dir() / "p3").exists()
        assert (artifacts_dir() / "p2").exists()
        assert (artifacts_dir() / "fail-old").exists()
        assert not (artifacts_dir() / "p1").exists()
    finally:
        repo._session.close()
        shutil.rmtree(case_dir, ignore_errors=True)


def test_prune_does_not_keep_failed_outside_history_window(monkeypatch) -> None:
    repo, case_dir = _repo(monkeypatch)
    try:
        repo.create_scenario("s1", "S", ["t1"])
        now = datetime.now(UTC)
        _make_run(repo, "fail-outside", status="failed", created_at=now + timedelta(seconds=0))
        _make_run(repo, "p1", status="finished", created_at=now + timedelta(seconds=1))
        _make_run(repo, "p2", status="finished", created_at=now + timedelta(seconds=2))
        _make_run(repo, "p3", status="finished", created_at=now + timedelta(seconds=3))

        deleted = prune_scenario_artifacts(
            repo,
            "s1",
            max_runs=2,
            max_days=None,
            keep_at_least_one_failed=True,
            history_max_runs=2,
            history_max_days=None,
        )

        assert deleted == 2
        assert (artifacts_dir() / "p3").exists()
        assert (artifacts_dir() / "p2").exists()
        assert not (artifacts_dir() / "fail-outside").exists()
        assert not (artifacts_dir() / "p1").exists()
    finally:
        repo._session.close()
        shutil.rmtree(case_dir, ignore_errors=True)


def test_prune_respects_max_days(monkeypatch) -> None:
    repo, case_dir = _repo(monkeypatch)
    try:
        repo.create_scenario("s1", "S", ["t1"])
        _make_run(repo, "old", status="failed", created_at=datetime.now(UTC) - timedelta(days=10))
        _make_run(repo, "new", status="failed", created_at=datetime.now(UTC))

        deleted = prune_scenario_artifacts(
            repo,
            "s1",
            max_runs=None,
            max_days=3,
            keep_at_least_one_failed=False,
            history_max_runs=None,
            history_max_days=None,
            now=datetime.now(UTC),
        )

        assert deleted == 1
        assert not (artifacts_dir() / "old").exists()
        assert (artifacts_dir() / "new").exists()
    finally:
        repo._session.close()
        shutil.rmtree(case_dir, ignore_errors=True)
