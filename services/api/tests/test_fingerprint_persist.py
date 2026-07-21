"""Fingerprints survive run prune — Given / When / Then."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from test_platform_contracts import CONTRACTS_VERSION, StepStatus, TestRunEvent, TestRunEventType

from test_platform_api.app import create_app
from test_platform_api.db import SqlAlchemyRepository, create_session_factory
from test_platform_api.redis_bus import InMemoryEventPublisher


def test_fingerprint_kept_after_failed_run_pruned() -> None:
    factory = create_session_factory("sqlite:///:memory:")
    publisher = InMemoryEventPublisher()
    client = TestClient(create_app(factory, publisher))

    client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.1.0",
            "contracts_version": CONTRACTS_VERSION,
            "tests": [{"id": "flaky_coin", "name": "Flaky", "steps": ["coin_flip"]}],
        },
    )
    scenario = client.post(
        "/scenarios",
        json={
            "name": "Flaky",
            "test_ids": ["flaky_coin"],
            "sut_version": "1.0.0",
            "history": {"max_runs": 1, "max_days": None},
        },
    ).json()

    failed = client.post(f"/scenarios/{scenario['id']}/runs").json()
    client.post(
        f"/runs/{failed['id']}/events",
        json={
            "run_id": failed["id"],
            "event_type": "step_failed",
            "test_id": "flaky_coin",
            "step_id": "coin_flip",
            "status": "failed",
            "message": "coin landed on tails (simulated flake)",
            "error_trace": "StepFailedError: coin landed on tails (simulated flake)",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    client.post(
        f"/runs/{failed['id']}/events",
        json={
            "run_id": failed["id"],
            "event_type": "run_failed",
            "status": "failed",
            "duration_ms": 2,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    history_after_fail = client.get(f"/scenarios/{scenario['id']}/history").json()
    assert len(history_after_fail["fingerprints"]) == 1
    assert history_after_fail["fingerprints"][0]["count"] == 1

    # Second run prunes the failed one (max_runs=1)
    passed = client.post(f"/scenarios/{scenario['id']}/runs").json()
    client.post(
        f"/runs/{passed['id']}/events",
        json={
            "run_id": passed["id"],
            "event_type": "run_finished",
            "status": "success",
            "duration_ms": 1,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    history = client.get(f"/scenarios/{scenario['id']}/history").json()
    assert len(history["runs"]) == 1
    assert history["runs"][0]["id"] == passed["id"]
    assert len(history["fingerprints"]) == 1
    assert history["fingerprints"][0]["count"] == 1
    assert history["fingerprints"][0]["recent_failures"][0]["run_id"] == failed["id"]


def test_append_step_failed_writes_occurrence_row() -> None:
    factory = create_session_factory("sqlite:///:memory:")
    session = factory()
    repo = SqlAlchemyRepository(session)
    repo.create_scenario("s1", "S", ["flaky_coin"], history_max_runs=1)
    repo.create_run("r1", "s1", sut_version="1.0.0", framework_version="0.1.0")
    repo.append_event(
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.STEP_FAILED,
            test_id="flaky_coin",
            step_id="coin_flip",
            status=StepStatus.FAILED,
            message="coin landed on tails (simulated flake)",
            error_trace="StepFailedError: coin landed on tails (simulated flake)",
            timestamp=datetime.now(UTC),
        )
    )
    session.commit()

    rows = repo.list_fingerprint_occurrences("s1")
    assert len(rows) == 1
    assert rows[0].step_id == "coin_flip"
    session.close()
