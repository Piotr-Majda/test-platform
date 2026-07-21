"""History duration falls back to run_finished event — Given / When / Then."""

from datetime import UTC, datetime

from test_platform_contracts import StepStatus, TestRunEvent, TestRunEventType

from test_platform_api.db import SqlAlchemyRepository, create_session_factory
from test_platform_api.history import scenario_duration_from_events


def test_scenario_duration_from_run_finished_event() -> None:
    events = [
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.RUN_STARTED,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.RUN_FINISHED,
            status=StepStatus.SUCCESS,
            duration_ms=871,
            timestamp=datetime.now(UTC),
        ),
    ]

    assert scenario_duration_from_events(events) == 871


def test_history_uses_event_duration_when_run_column_null() -> None:
    # Given — mimic Redis ingest that stored events but not run.duration_ms
    factory = create_session_factory("sqlite:///:memory:")
    session = factory()
    repo = SqlAlchemyRepository(session)
    repo.create_scenario("s1", "Smoke", ["google_title"])
    repo.create_run("r1", "s1", sut_version="1.0.0", framework_version="0.1.0")
    repo.update_run_status("r1", "finished")
    repo.append_event(
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.RUN_FINISHED,
            status=StepStatus.SUCCESS,
            duration_ms=871,
            timestamp=datetime.now(UTC),
        )
    )
    session.commit()
    session.close()

    from fastapi.testclient import TestClient

    from test_platform_api.app import create_app
    from test_platform_api.redis_bus import InMemoryEventPublisher

    client = TestClient(create_app(factory, InMemoryEventPublisher()))
    history = client.get("/scenarios/s1/history").json()

    assert history["runs"][0]["duration_ms"] == 871
