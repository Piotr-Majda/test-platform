"""History prune + flakiness — Given / When / Then."""

from fastapi.testclient import TestClient
from test_platform_contracts import CONTRACTS_VERSION

from test_platform_api.app import create_app
from test_platform_api.db import create_session_factory
from test_platform_api.history import compute_flakiness
from test_platform_api.redis_bus import InMemoryEventPublisher


def _client() -> tuple[TestClient, InMemoryEventPublisher]:
    factory = create_session_factory("sqlite:///:memory:")
    publisher = InMemoryEventPublisher()
    return TestClient(create_app(factory, publisher)), publisher


def test_flakiness_fail_rate() -> None:
    stats = compute_flakiness(
        [("finished", 100), ("failed", 120), ("failed", 90)],
        test_id="google_title",
        sut_version="1.0.0",
        framework_version="0.1.0",
    )
    assert stats.total_runs == 3
    assert stats.failed_runs == 2
    assert stats.fail_rate == 2 / 3
    assert stats.avg_duration_ms is not None
    assert abs(stats.avg_duration_ms - (310 / 3)) < 0.01


def test_prune_keeps_intersection_of_days_and_runs() -> None:
    client, _publisher = _client()
    client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.1.0",
            "contracts_version": CONTRACTS_VERSION,
            "tests": [{"id": "google_title", "name": "Google", "steps": []}],
        },
    )
    scenario = client.post(
        "/scenarios",
        json={
            "name": "H",
            "test_ids": ["google_title"],
            "sut_version": "1.0.0",
            "history": {"max_runs": 2, "max_days": 30},
        },
    ).json()

    # create 3 runs via API; prune on each write — after 3rd only 2 remain
    for _ in range(3):
        client.post(f"/scenarios/{scenario['id']}/runs")

    history = client.get(f"/scenarios/{scenario['id']}/history").json()
    assert len(history["runs"]) == 2


def test_scenario_history_includes_versions_and_flakiness() -> None:
    client, _publisher = _client()
    client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.2.0",
            "contracts_version": CONTRACTS_VERSION,
            "tests": [{"id": "google_title", "name": "Google", "steps": ["open_page"]}],
        },
    )
    scenario = client.post(
        "/scenarios",
        json={
            "name": "H",
            "test_ids": ["google_title"],
            "sut_version": "2.1.0",
            "history": {"max_runs": 50, "max_days": None},
        },
    ).json()
    run = client.post(f"/scenarios/{scenario['id']}/runs").json()
    assert run["sut_version"] == "2.1.0"
    assert run["framework_version"] == "0.2.0"

    # mark finished via event ingest
    from datetime import UTC, datetime

    client.post(
        f"/runs/{run['id']}/events",
        json={
            "run_id": run["id"],
            "event_type": "test_finished",
            "test_id": "google_title",
            "duration_ms": 400,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    client.post(
        f"/runs/{run['id']}/events",
        json={
            "run_id": run["id"],
            "event_type": "run_finished",
            "duration_ms": 450,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    history = client.get(f"/scenarios/{scenario['id']}/history").json()
    assert history["runs"][0]["sut_version"] == "2.1.0"
    assert history["runs"][0]["framework_version"] == "0.2.0"
    assert history["runs"][0]["status"] == "finished"
    assert history["runs"][0]["duration_ms"] == 450
    assert history["flakiness"][0]["fail_rate"] == 0.0
    assert history["flakiness"][0]["test_id"] == "google_title"


def test_update_scenario_sut_version() -> None:
    client, _publisher = _client()
    client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.1.0",
            "contracts_version": CONTRACTS_VERSION,
            "tests": [{"id": "a", "name": "A", "steps": []}],
        },
    )
    scenario = client.post(
        "/scenarios",
        json={"name": "S", "test_ids": ["a"], "sut_version": "1.0.0"},
    ).json()

    updated = client.patch(
        f"/scenarios/{scenario['id']}",
        json={"sut_version": "1.1.0", "history": {"max_runs": 10, "max_days": 7}},
    ).json()

    assert updated["sut_version"] == "1.1.0"
    assert updated["history"]["max_runs"] == 10
    assert updated["history"]["max_days"] == 7
