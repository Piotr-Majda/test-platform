"""Event ingest from stream consumer — Given / When / Then."""

from datetime import UTC, datetime

from test_platform_contracts import (
    StepStatus,
    TestRunEvent,
    TestRunEventType,
)

from test_platform_api.db import SqlAlchemyRepository, create_session_factory
from test_platform_api.event_ingest import apply_event


def test_apply_run_started_sets_running() -> None:
    # Given
    factory = create_session_factory("sqlite:///:memory:")
    session = factory()
    repo = SqlAlchemyRepository(session)
    repo.create_scenario("s1", "Smoke", ["google_title"])
    repo.create_run("r1", "s1", sut_version="1.0.0", framework_version="0.1.0")
    event = TestRunEvent(
        run_id="r1",
        event_type=TestRunEventType.RUN_STARTED,
        timestamp=datetime.now(UTC),
    )

    # When
    apply_event(repo, event)
    session.commit()
    run = repo.get_run("r1")

    # Then
    assert run is not None
    assert run.status == "running"
    session.close()


def test_apply_run_finished_stores_duration() -> None:
    # Given
    factory = create_session_factory("sqlite:///:memory:")
    session = factory()
    repo = SqlAlchemyRepository(session)
    repo.create_scenario("s1", "Smoke", ["google_title"])
    repo.create_run("r1", "s1", sut_version="1.0.0", framework_version="0.1.0")
    event = TestRunEvent(
        run_id="r1",
        event_type=TestRunEventType.RUN_FINISHED,
        status=StepStatus.SUCCESS,
        duration_ms=123,
        timestamp=datetime.now(UTC),
    )

    # When
    apply_event(repo, event)
    session.commit()
    run = repo.get_run("r1")

    # Then
    assert run is not None
    assert run.status == "finished"
    assert run.duration_ms == 123
    session.close()


def test_apply_step_failed_stores_trace() -> None:
    # Given
    factory = create_session_factory("sqlite:///:memory:")
    session = factory()
    repo = SqlAlchemyRepository(session)
    repo.create_scenario("s1", "Smoke", ["google_title"])
    repo.create_run("r1", "s1", sut_version="1.0.0", framework_version="0.1.0")
    event = TestRunEvent(
        run_id="r1",
        event_type=TestRunEventType.STEP_FAILED,
        step_id="assert_title",
        status=StepStatus.FAILED,
        error_trace="AssertionError: boom",
        timestamp=datetime.now(UTC),
    )

    # When
    apply_event(repo, event)
    session.commit()
    events = repo.list_events("r1")

    # Then
    assert events[0].error_trace == "AssertionError: boom"
    session.close()
