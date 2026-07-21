"""API run orchestration — Given / When / Then."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from test_platform_contracts import (
    CONTRACTS_VERSION,
    StepStatus,
    TestRunEvent,
    TestRunEventType,
)

from test_platform_api.app import create_app
from test_platform_api.db import create_session_factory
from test_platform_api.redis_bus import InMemoryEventPublisher


def _client() -> tuple[TestClient, InMemoryEventPublisher]:
    factory = create_session_factory("sqlite:///:memory:")
    publisher = InMemoryEventPublisher()
    app = create_app(factory, publisher)
    return TestClient(app), publisher


def _manifest(*, plugin_id: str = "example", tests: list[dict], framework_version: str = "0.1.0") -> dict:
    return {
        "plugin_id": plugin_id,
        "framework_version": framework_version,
        "contracts_version": CONTRACTS_VERSION,
        "tests": tests,
    }


def test_register_and_list_tests() -> None:
    # Given
    client, _publisher = _client()
    payload = _manifest(
        tests=[
            {
                "id": "google_title",
                "name": "Google page title",
                "description": "Opens Google and reads title",
                "steps": ["open_page", "assert_title"],
            }
        ],
    )

    # When
    register = client.post("/plugins/manifest", json=payload)
    listed = client.get("/tests")

    # Then
    assert register.status_code == 204
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == "google_title"


def test_start_run_publishes_execute_command() -> None:
    # Given
    client, publisher = _client()
    client.post(
        "/plugins/manifest",
        json=_manifest(
            tests=[
                {
                    "id": "google_title",
                    "name": "Google page title",
                    "steps": ["open_page"],
                }
            ],
        ),
    )
    scenario = client.post(
        "/scenarios",
        json={"name": "Smoke", "test_ids": ["google_title"]},
    ).json()

    # When
    run = client.post(f"/scenarios/{scenario['id']}/runs")

    # Then
    assert run.status_code == 201
    assert run.json()["status"] == "queued"
    assert len(publisher.commands) == 1
    assert publisher.commands[0].test_ids == ["google_title"]


def test_ingest_event_updates_run_status() -> None:
    # Given
    client, _publisher = _client()
    client.post(
        "/plugins/manifest",
        json=_manifest(tests=[{"id": "google_title", "name": "Google", "steps": []}]),
    )
    scenario = client.post(
        "/scenarios",
        json={"name": "Smoke", "test_ids": ["google_title"]},
    ).json()
    run = client.post(f"/scenarios/{scenario['id']}/runs").json()
    event = TestRunEvent(
        run_id=run["id"],
        event_type=TestRunEventType.STEP_FAILED,
        step_id="assert_title",
        status=StepStatus.FAILED,
        message="title mismatch",
        error_trace="AssertionError",
        timestamp=datetime.now(UTC),
        contracts_version=CONTRACTS_VERSION,
    )

    # When
    ingest = client.post(f"/runs/{run['id']}/events", json=event.model_dump(mode="json"))
    finished = TestRunEvent(
        run_id=run["id"],
        event_type=TestRunEventType.RUN_FAILED,
        message="run failed",
        timestamp=datetime.now(UTC),
    )
    client.post(f"/runs/{run['id']}/events", json=finished.model_dump(mode="json"))
    detail = client.get(f"/runs/{run['id']}")

    # Then
    assert ingest.status_code == 204
    body = detail.json()
    assert body["status"] == "failed"
    assert any(e["event_type"] == "step_failed" for e in body["events"])


def test_create_scenario_with_ordered_tests() -> None:
    # Given
    client, _publisher = _client()
    client.post(
        "/plugins/manifest",
        json=_manifest(
            tests=[
                {"id": "a", "name": "A", "steps": []},
                {"id": "b", "name": "B", "steps": []},
            ],
        ),
    )

    # When
    response = client.post("/scenarios", json={"name": "Ordered", "test_ids": ["b", "a"]})

    # Then
    assert response.status_code == 201
    body = response.json()
    assert body["test_ids"] == ["b", "a"]
    assert body["artifacts"]["max_runs"] == 20
    assert body["artifacts"]["keep_at_least_one_failed"] is True


def test_update_scenario_reorders_tests_and_sets_artifact_retention() -> None:
    client, _publisher = _client()
    client.post(
        "/plugins/manifest",
        json=_manifest(
            tests=[
                {"id": "a", "name": "A", "steps": []},
                {"id": "b", "name": "B", "steps": []},
            ],
        ),
    )
    created = client.post(
        "/scenarios",
        json={
            "name": "Ordered",
            "test_ids": ["a", "b"],
            "sut_version": "1.0.0",
            "history": {"max_runs": 50, "max_days": None},
            "artifacts": {"max_runs": 20, "max_days": None, "keep_at_least_one_failed": True},
        },
    ).json()

    updated = client.patch(
        f"/scenarios/{created['id']}",
        json={
            "test_ids": ["b", "a"],
            "sut_version": "2.0.0",
            "history": {"max_runs": 10, "max_days": 7},
            "artifacts": {"max_runs": 5, "max_days": 3, "keep_at_least_one_failed": False},
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["test_ids"] == ["b", "a"]
    assert body["sut_version"] == "2.0.0"
    assert body["history"] == {"max_runs": 10, "max_days": 7}
    assert body["artifacts"] == {
        "max_runs": 5,
        "max_days": 3,
        "keep_at_least_one_failed": False,
    }


def test_delete_scenario_removes_it_from_list() -> None:
    client, _publisher = _client()
    client.post(
        "/plugins/manifest",
        json=_manifest(tests=[{"id": "a", "name": "A", "steps": []}]),
    )
    scenario = client.post("/scenarios", json={"name": "Temp", "test_ids": ["a"]}).json()

    deleted = client.delete(f"/scenarios/{scenario['id']}")
    listed = client.get("/scenarios")

    assert deleted.status_code == 204
    assert listed.json() == []
