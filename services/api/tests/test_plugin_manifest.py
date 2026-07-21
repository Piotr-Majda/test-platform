"""Plugin manifest registration — Given / When / Then."""

from fastapi.testclient import TestClient
from test_platform_contracts import CONTRACTS_VERSION, LOG_SCHEMA_VERSION

from test_platform_api.app import create_app
from test_platform_api.db import create_session_factory
from test_platform_api.redis_bus import InMemoryEventPublisher


def _client() -> TestClient:
    factory = create_session_factory("sqlite:///:memory:")
    return TestClient(create_app(factory, InMemoryEventPublisher()))


def test_register_manifest_lists_tests() -> None:
    client = _client()

    response = client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.1.0",
            "contracts_version": CONTRACTS_VERSION,
            "tests": [
                {
                    "id": "google_title",
                    "name": "Google page title",
                    "steps": ["open_page", "assert_title"],
                }
            ],
        },
    )
    listed = client.get("/tests")

    assert response.status_code == 204
    assert listed.json()[0]["id"] == "google_title"


def test_register_manifest_rejects_contracts_version_mismatch() -> None:
    client = _client()

    response = client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.1.0",
            "contracts_version": "0.0.0",
            "tests": [],
        },
    )

    assert response.status_code == 409
    assert "contracts_version" in response.json()["detail"]


def test_register_manifest_rejects_log_schema_version_mismatch() -> None:
    client = _client()

    response = client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.1.0",
            "contracts_version": CONTRACTS_VERSION,
            "log_schema_version": LOG_SCHEMA_VERSION,
            "log_schema_version": "0.0",
            "tests": [],
        },
    )

    assert response.status_code == 409
    assert "log_schema_version" in response.json()["detail"]


def test_register_manifest_replaces_plugin_catalog() -> None:
    client = _client()
    client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.1.0",
            "contracts_version": CONTRACTS_VERSION,
            "tests": [
                {"id": "old_test", "name": "Old", "steps": []},
                {"id": "keep_test", "name": "Keep", "steps": []},
            ],
        },
    )

    client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.2.0",
            "contracts_version": CONTRACTS_VERSION,
            "tests": [
                {"id": "keep_test", "name": "Keep updated", "steps": ["step_a"]},
                {"id": "new_test", "name": "New", "steps": []},
            ],
        },
    )
    listed = client.get("/tests").json()
    ids = {t["id"] for t in listed}

    assert ids == {"keep_test", "new_test"}
    keep = next(t for t in listed if t["id"] == "keep_test")
    assert keep["name"] == "Keep updated"
    assert keep["steps"] == ["step_a"]
