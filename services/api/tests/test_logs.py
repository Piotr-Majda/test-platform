"""Semantic structured-log endpoints â€” Given / When / Then."""

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from test_platform_contracts import (
    ArtifactKind,
    ArtifactRef,
    StepStatus,
    TestRunEvent,
    TestRunEventType,
)

from test_platform_api.app import create_app
from test_platform_api.db import create_session_factory
from test_platform_api.redis_bus import InMemoryEventPublisher


class MemoryArtifacts:
    def __init__(self, values: dict[str, dict]) -> None:
        self.values = values

    def read_bytes(self, key: str) -> bytes | None:
        value = self.values.get(key)
        return json.dumps(value).encode() if value is not None else None


def _run(client: TestClient) -> str:
    client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "1.0",
            "contracts_version": "0.8.0",
            "tests": [{"id": "checkout", "name": "Checkout", "steps": ["pay"]}],
        },
    )
    scenario = client.post(
        "/scenarios", json={"name": "Checkout", "test_ids": ["checkout"]}
    ).json()
    return client.post(f"/scenarios/{scenario['id']}/runs").json()["id"]


def test_api_returns_versioned_test_and_step_logs(monkeypatch) -> None:
    factory = create_session_factory("sqlite:///:memory:")
    client = TestClient(create_app(factory, InMemoryEventPublisher()))
    run_id = _run(client)
    key = f"{run_id}/checkout/pay/step.log.json"
    event = TestRunEvent(
        run_id=run_id,
        event_type=TestRunEventType.STEP_FINISHED,
        test_id="checkout",
        step_id="pay",
        status=StepStatus.SUCCESS,
        duration_ms=21,
        artifacts=[
            ArtifactRef(
                id="log-1",
                kind=ArtifactKind.LOG,
                name="step.log.json",
                content_type="application/json",
                relative_path=key,
            )
        ],
        timestamp=datetime.now(UTC),
    )
    client.post(f"/runs/{run_id}/events", json=event.model_dump(mode="json"))
    storage = MemoryArtifacts(
        {
            key: {
                "schema_version": "1.0",
                "scope": "step",
                "test_id": "checkout",
                "step_id": "pay",
                "status": "success",
                "duration_ms": 21,
                "entries": [
                    {
                        "timestamp": "2026-07-21T12:00:00Z",
                        "layer": "adapter",
                        "component": "stripe",
                        "message": "Payment accepted",
                        "duration_ms": 20,
                    }
                ],
            }
        }
    )
    monkeypatch.setattr("test_platform_api.app.artifact_storage", lambda: storage)

    step = client.get(f"/runs/{run_id}/tests/checkout/steps/pay/logs")
    test = client.get(f"/runs/{run_id}/tests/checkout/logs")

    assert step.status_code == 200
    assert step.json()["schema_version"] == "1.0"
    assert step.json()["entries"][0]["component"] == "stripe"
    assert test.status_code == 200
    assert test.json()["steps"][0]["step_id"] == "pay"


def test_api_adapts_legacy_time_and_step_fields(monkeypatch) -> None:
    factory = create_session_factory("sqlite:///:memory:")
    client = TestClient(create_app(factory, InMemoryEventPublisher()))
    run_id = _run(client)
    storage = MemoryArtifacts(
        {
            f"{run_id}/checkout/test.log.json": {
                "test_id": "checkout",
                "steps": [
                    {
                        "step": "pay",
                        "status": "success",
                        "entries": [
                            {
                                "time": "2026-07-21T12:00:00Z",
                                "layer": "framework",
                                "message": "legacy log",
                            }
                        ],
                    }
                ],
            }
        }
    )
    monkeypatch.setattr("test_platform_api.app.artifact_storage", lambda: storage)

    response = client.get(f"/runs/{run_id}/tests/checkout/logs")

    assert response.status_code == 200
    assert response.json()["schema_version"] == "1.0"
    assert response.json()["steps"][0]["step_id"] == "pay"
    assert response.json()["steps"][0]["entries"][0]["timestamp"].startswith("2026-07-21")
