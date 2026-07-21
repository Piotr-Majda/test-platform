"""pytest plugin: fixture injects emitter; hooks emit test + scenario totals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from test_platform_contracts import StepStatus, TestRunEvent, TestRunEventType

from test_platform_executor.framework.emission import (
    clear_emission_context,
    set_emission_context,
    set_test_id,
    take_test_action_ms,
)

if TYPE_CHECKING:
    from test_platform_executor.events import ProgressPublisher

_publisher: ProgressPublisher | None = None
_run_id: str | None = None
_selected_test_ids: set[str] = set()
_scenario_action_ms: int = 0


def configure_platform_run(
    publisher: ProgressPublisher,
    run_id: str,
    test_ids: list[str],
) -> None:
    global _publisher, _run_id, _selected_test_ids, _scenario_action_ms
    _publisher = publisher
    _run_id = run_id
    _selected_test_ids = set(test_ids)
    _scenario_action_ms = 0


def _emit(event: TestRunEvent) -> None:
    if _publisher is None:
        return
    _publisher.publish(event)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("test-platform")
    group.addoption("--platform-run-id", action="store", default="")
    group.addoption("--platform-test-ids", action="store", default="")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "platform_test(id): platform catalog test id")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    selected = _selected_test_ids
    if not selected:
        raw = config.getoption("--platform-test-ids") or ""
        selected = {part for part in raw.split(",") if part}
    if not selected:
        return
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        marker = item.get_closest_marker("platform_test")
        test_id = marker.args[0] if marker and marker.args else None
        if test_id in selected:
            kept.append(item)
        else:
            deselected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = kept


@pytest.fixture
def platform_emitter():
    if _publisher is None or _run_id is None:
        raise RuntimeError("platform run not configured")

    def emit(event: TestRunEvent) -> None:
        _publisher.publish(event)

    set_emission_context(emitter=emit, run_id=_run_id)
    yield emit
    clear_emission_context()


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    marker = item.get_closest_marker("platform_test")
    if marker and marker.args:
        set_test_id(str(marker.args[0]))
        if _run_id:
            _emit(
                TestRunEvent(
                    run_id=_run_id,
                    event_type=TestRunEventType.TEST_STARTED,
                    test_id=str(marker.args[0]),
                    status=StepStatus.RUNNING,
                    message=f"test started: {marker.args[0]}",
                    timestamp=datetime.now(UTC),
                )
            )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    global _scenario_action_ms
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or _run_id is None:
        return
    marker = item.get_closest_marker("platform_test")
    test_id = str(marker.args[0]) if marker and marker.args else item.name
    # Sum of step SUT action times — not pytest wall clock / logging / emit
    duration_ms = take_test_action_ms()
    _scenario_action_ms += duration_ms
    if report.passed:
        _emit(
            TestRunEvent(
                run_id=_run_id,
                event_type=TestRunEventType.TEST_FINISHED,
                test_id=test_id,
                status=StepStatus.SUCCESS,
                message=f"test finished: {test_id}",
                duration_ms=duration_ms,
                timestamp=datetime.now(UTC),
            )
        )
    elif report.failed:
        _emit(
            TestRunEvent(
                run_id=_run_id,
                event_type=TestRunEventType.TEST_FAILED,
                test_id=test_id,
                status=StepStatus.FAILED,
                message=str(report.longrepr),
                error_trace=str(report.longrepr),
                duration_ms=duration_ms,
                timestamp=datetime.now(UTC),
            )
        )


def pytest_sessionstart(session: pytest.Session) -> None:
    global _scenario_action_ms
    _scenario_action_ms = 0
    if _run_id:
        _emit(
            TestRunEvent(
                run_id=_run_id,
                event_type=TestRunEventType.RUN_STARTED,
                status=StepStatus.RUNNING,
                message="scenario run started",
                timestamp=datetime.now(UTC),
            )
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _run_id is None:
        return
    failed = exitstatus != 0
    _emit(
        TestRunEvent(
            run_id=_run_id,
            event_type=TestRunEventType.RUN_FAILED if failed else TestRunEventType.RUN_FINISHED,
            status=StepStatus.FAILED if failed else StepStatus.SUCCESS,
            message="scenario run finished",
            duration_ms=_scenario_action_ms,
            timestamp=datetime.now(UTC),
        )
    )
