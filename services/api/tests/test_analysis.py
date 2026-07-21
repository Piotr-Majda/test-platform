"""Manual AI / heuristic analysis — Given / When / Then."""

from datetime import UTC, datetime
import time

from fastapi.testclient import TestClient
from test_platform_contracts import (
    CONTRACTS_VERSION,
    AnalysisScope,
    StepStatus,
    TestRunEvent,
    TestRunEventType,
)

from test_platform_api.analysis import HeuristicFailureAnalyzer
from test_platform_api.app import create_app
from test_platform_api.db import create_session_factory
from test_platform_api.redis_bus import InMemoryEventPublisher


def _client() -> TestClient:
    factory = create_session_factory("sqlite:///:memory:")
    return TestClient(
        create_app(factory, InMemoryEventPublisher(), analyzer=HeuristicFailureAnalyzer())
    )


def _wait_job(client: TestClient, job_id: str, *, timeout_s: float = 5.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        response = client.get(f"/analyses/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"analysis job {job_id} did not finish in {timeout_s}s")


def _seed_failed_scenario(client: TestClient) -> tuple[str, str, str]:
    client.post(
        "/plugins/manifest",
        json={
            "plugin_id": "example",
            "framework_version": "0.1.0",
            "contracts_version": CONTRACTS_VERSION,
            "tests": [
                {"id": "a", "name": "A", "steps": ["step_a"]},
                {"id": "b", "name": "B", "steps": ["step_b"]},
            ],
        },
    )
    scenario = client.post(
        "/scenarios",
        json={
            "name": "Multi",
            "test_ids": ["a", "b"],
            "sut_version": "1.0.0",
            "history": {"max_runs": 50, "max_days": None},
        },
    ).json()
    run = client.post(f"/scenarios/{scenario['id']}/runs").json()
    for test_id, step_id in (("a", "step_a"), ("b", "step_b")):
        event = TestRunEvent(
            run_id=run["id"],
            event_type=TestRunEventType.STEP_FAILED,
            test_id=test_id,
            step_id=step_id,
            status=StepStatus.FAILED,
            message="Timeout waiting for SUT",
            error_trace="TimeoutError: Timeout waiting for SUT",
            timestamp=datetime.now(UTC),
            contracts_version=CONTRACTS_VERSION,
        )
        client.post(f"/runs/{run['id']}/events", json=event.model_dump(mode="json"))
    client.post(
        f"/runs/{run['id']}/events",
        json=TestRunEvent(
            run_id=run["id"],
            event_type=TestRunEventType.RUN_FAILED,
            message="failed",
            timestamp=datetime.now(UTC),
            contracts_version=CONTRACTS_VERSION,
        ).model_dump(mode="json"),
    )
    return scenario["id"], run["id"], "Timeout waiting for SUT"


def test_analyze_scenario_lists_errors_and_flakiness() -> None:
    client = _client()
    scenario_id, run_id, _ = _seed_failed_scenario(client)

    started = client.post(
        "/analyses",
        json={"scope": "scenario", "scenario_id": scenario_id},
    )
    assert started.status_code == 202
    job = _wait_job(client, started.json()["id"])
    assert job["status"] == "completed"
    body = job["report"]
    assert body["scope"] == AnalysisScope.SCENARIO
    assert body["scenario_id"] == scenario_id
    assert len(body["errors"]) == 1
    err = body["errors"][0]
    assert err["last_failure_run_id"] == run_id
    assert {(w["test_id"], w["step_id"]) for w in err["where"]} == {("a", "step_a"), ("b", "step_b")}
    assert err["occurrence_count"] == 2
    assert err["given"]
    assert err["when_steps"]
    assert err["then_actual"]
    assert err["expected"]
    assert 0 <= err["confidence_pct"] <= 100
    assert body["scenario_name"] == "Multi"


def test_export_analysis_zip_contains_markdown() -> None:
    client = _client()
    scenario_id, _, _ = _seed_failed_scenario(client)
    started = client.post(
        "/analyses",
        json={"scope": "scenario", "scenario_id": scenario_id},
    ).json()
    job = _wait_job(client, started["id"])
    report_id = job["report"]["id"]

    exported = client.get(f"/analyses/{report_id}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")
    assert exported.content[:2] == b"PK"


def test_analyze_run_scopes_single_run() -> None:
    client = _client()
    _scenario_id, run_id, _ = _seed_failed_scenario(client)

    started = client.post("/analyses", json={"scope": "run", "run_id": run_id})
    assert started.status_code == 202
    job = _wait_job(client, started.json()["id"])
    assert job["status"] == "completed"
    body = job["report"]
    assert body["scope"] == "run"
    assert body["run_id"] == run_id
    assert body["errors"]
    assert all(e["last_failure_run_id"] == run_id for e in body["errors"])
    assert len(body["test_analyses"]) == 2
    assert {t["test_id"] for t in body["test_analyses"]} == {"a", "b"}
    assert body["scenario_reliability"] == "failed"
    assert body["flakiness"] == []

    bundle = client.get(f"/runs/{run_id}/analysis")
    assert bundle.status_code == 200
    assert bundle.json()["run"]["id"] == body["id"]
    assert set(bundle.json()["tests"]) == {"a", "b"}

    for test_id in ("a", "b"):
        test_report = client.get(f"/runs/{run_id}/tests/{test_id}/analysis")
        assert test_report.status_code == 200
        assert test_report.json()["test_id"] == test_id
        assert test_report.json()["scope"] == "test"
        assert test_report.json()["flakiness"] == []


def test_analyze_test_scope() -> None:
    client = _client()
    _scenario_id, run_id, _ = _seed_failed_scenario(client)
    started = client.post(
        "/analyses",
        json={"scope": "test", "run_id": run_id, "test_id": "a"},
    )
    assert started.status_code == 202
    job = _wait_job(client, started.json()["id"])
    assert job["status"] == "completed"
    body = job["report"]
    assert body["scope"] == "test"
    assert body["test_id"] == "a"
    assert body["run_id"] == run_id
    assert body["errors"]
    assert all(w["test_id"] == "a" for e in body["errors"] for w in e["where"])
    assert body["flakiness"] == []


def test_analyze_passed_test_has_no_history_errors() -> None:
    """Green test must not inherit fingerprint errors from other runs/tests."""
    client = _client()
    scenario_id, _failed_run_id, _ = _seed_failed_scenario(client)
    run = client.post(f"/scenarios/{scenario_id}/runs").json()
    for test_id in ("a", "b"):
        client.post(
            f"/runs/{run['id']}/events",
            json=TestRunEvent(
                run_id=run["id"],
                event_type=TestRunEventType.TEST_FINISHED,
                test_id=test_id,
                status=StepStatus.SUCCESS,
                timestamp=datetime.now(UTC),
                contracts_version=CONTRACTS_VERSION,
            ).model_dump(mode="json"),
        )
    client.post(
        f"/runs/{run['id']}/events",
        json=TestRunEvent(
            run_id=run["id"],
            event_type=TestRunEventType.RUN_FINISHED,
            message="ok",
            timestamp=datetime.now(UTC),
            contracts_version=CONTRACTS_VERSION,
        ).model_dump(mode="json"),
    )
    job = _wait_job(
        client,
        client.post(
            "/analyses",
            json={"scope": "test", "run_id": run["id"], "test_id": "a"},
        ).json()["id"],
    )
    assert job["status"] == "completed"
    body = job["report"]
    assert body["errors"] == []
    assert body["scenario_reliability"] in {"passed", "watch"}
    assert body["flakiness"] == []


def test_analyze_fingerprint_requires_ids() -> None:
    client = _client()
    response = client.post("/analyses", json={"scope": "fingerprint", "fingerprint": "abc"})
    assert response.status_code == 422


def test_get_analysis_by_id_after_job_completes() -> None:
    client = _client()
    scenario_id, _, _ = _seed_failed_scenario(client)
    started = client.post(
        "/analyses",
        json={"scope": "scenario", "scenario_id": scenario_id},
    ).json()
    job = _wait_job(client, started["id"])
    report_id = job["report"]["id"]

    fetched = client.get(f"/analyses/{report_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == report_id
