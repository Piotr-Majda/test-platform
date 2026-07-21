"""pytest hybrid runner — Given / When / Then."""

from pathlib import Path

from test_platform_contracts import CONTRACTS_VERSION, ExecuteTestCommand, TestRunEventType

from test_platform_executor.events import InMemoryProgressPublisher
from test_platform_executor.handler import process_execute_command


def test_pytest_run_emits_step_test_and_scenario_events(monkeypatch) -> None:
    artifacts = Path(__file__).resolve().parent / "_tmp_artifacts_run"
    artifacts.mkdir(exist_ok=True)
    monkeypatch.setenv("ARTIFACTS_DIR", str(artifacts))
    monkeypatch.setenv(
        "PLATFORM_FAKE_HTML",
        "<html><title>Google</title></html>",
    )
    publisher = InMemoryProgressPublisher()
    command = ExecuteTestCommand(
        run_id="run-pytest-1",
        scenario_id="scenario-1",
        test_ids=["google_title"],
        contracts_version=CONTRACTS_VERSION,
    )

    ok = process_execute_command(command, publisher)

    assert ok is True
    types = {e.event_type for e in publisher.events}
    assert TestRunEventType.STEP_FINISHED in types
    assert TestRunEventType.TEST_FINISHED in types
    assert TestRunEventType.RUN_FINISHED in types
    scenario = next(e for e in publisher.events if e.event_type == TestRunEventType.RUN_FINISHED)
    assert scenario.duration_ms is not None


def test_pytest_failed_title_emits_step_failed(monkeypatch) -> None:
    artifacts = Path(__file__).resolve().parent / "_tmp_artifacts_run_fail"
    artifacts.mkdir(exist_ok=True)
    monkeypatch.setenv("ARTIFACTS_DIR", str(artifacts))
    monkeypatch.setenv(
        "PLATFORM_FAKE_HTML",
        "<html><title>Other</title></html>",
    )
    publisher = InMemoryProgressPublisher()
    command = ExecuteTestCommand(
        run_id="run-pytest-2",
        scenario_id="scenario-1",
        test_ids=["google_title"],
    )

    ok = process_execute_command(command, publisher)

    assert ok is False
    types = {e.event_type for e in publisher.events}
    assert TestRunEventType.STEP_FAILED in types
    assert TestRunEventType.RUN_FAILED in types
