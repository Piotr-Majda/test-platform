from fastapi.testclient import TestClient

from test_platform_api.app import create_app
from test_platform_api.auth import AuthConfig
from test_platform_api.db import create_session_factory
from test_platform_api.redis_bus import InMemoryEventPublisher


def _client() -> TestClient:
    factory = create_session_factory("sqlite:///:memory:")
    return TestClient(
        create_app(
            factory,
            InMemoryEventPublisher(),
            auth_config=AuthConfig(
                enabled=True,
                admin_password="admin-secret",
                viewer_password="viewer-secret",
                secret="test-signing-secret",
                secure_cookie=False,
            ),
        )
    )


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()


def test_login_required_and_invalid_credentials_rejected() -> None:
    client = _client()

    assert client.get("/scenarios").status_code == 401
    assert client.post(
        "/auth/login", json={"username": "viewer", "password": "wrong"}
    ).status_code == 401
    assert client.get("/health").status_code == 200


def test_viewer_can_read_run_and_analyze_but_cannot_manage_scenarios() -> None:
    client = _client()
    _login(client, "admin", "admin-secret")
    scenario = client.post(
        "/scenarios", json={"name": "Demo", "test_ids": ["checkout"]}
    ).json()

    client.post("/auth/logout")
    user = _login(client, "viewer", "viewer-secret")
    assert user == {"username": "viewer", "role": "viewer"}
    assert client.get("/auth/me").json() == user
    assert client.get("/scenarios").status_code == 200
    assert client.post(f"/scenarios/{scenario['id']}/runs").status_code == 201
    assert client.post(
        "/analyses", json={"scope": "scenario", "scenario_id": scenario["id"]}
    ).status_code == 202
    assert client.post(
        "/scenarios", json={"name": "Forbidden", "test_ids": ["checkout"]}
    ).status_code == 403
    assert client.patch(
        f"/scenarios/{scenario['id']}", json={"name": "Forbidden"}
    ).status_code == 403
    assert client.delete(f"/scenarios/{scenario['id']}").status_code == 403


def test_admin_can_manage_scenarios_and_logout_clears_session() -> None:
    client = _client()
    user = _login(client, "admin", "admin-secret")
    assert user["role"] == "admin"

    created = client.post(
        "/scenarios", json={"name": "Admin scenario", "test_ids": ["checkout"]}
    )
    assert created.status_code == 201
    scenario_id = created.json()["id"]
    assert client.patch(f"/scenarios/{scenario_id}", json={"name": "Updated"}).status_code == 200
    assert client.delete(f"/scenarios/{scenario_id}").status_code == 204

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
