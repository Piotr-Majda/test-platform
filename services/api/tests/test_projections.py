"""Run projection for UI step table — Given / When / Then."""

from datetime import UTC, datetime

from test_platform_contracts import (
    ArtifactKind,
    ArtifactRef,
    StepStatus,
    TestRunEvent,
    TestRunEventType,
)

from test_platform_api.projections import project_run


def test_project_run_builds_step_rows_with_duration() -> None:
    events = [
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.STEP_FINISHED,
            test_id="google_title",
            step_id="open_page",
            status=StepStatus.SUCCESS,
            duration_ms=12,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.STEP_FAILED,
            test_id="google_title",
            step_id="assert_title",
            status=StepStatus.FAILED,
            message="expected title to contain 'Google', got 'Other'",
            error_trace="StepFailedError: expected title to contain 'Google', got 'Other'",
            duration_ms=3,
            artifacts=[
                ArtifactRef(
                    id="a1",
                    kind=ArtifactKind.HTML_SNAPSHOT,
                    name="page.html",
                    content_type="text/html",
                    relative_path="r1/assert_title/page.html",
                )
            ],
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.TEST_FAILED,
            test_id="google_title",
            duration_ms=20,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.RUN_FAILED,
            duration_ms=25,
            timestamp=datetime.now(UTC),
        ),
    ]

    projection = project_run(events)

    assert projection.steps[0].name == "open_page"
    assert projection.steps[0].duration_ms == 12
    assert projection.steps[1].error_message == "expected title to contain 'Google', got 'Other'"
    assert projection.steps[1].error_trace is not None
    assert projection.steps[1].artifacts[0].kind == ArtifactKind.HTML_SNAPSHOT
    assert projection.tests[0].duration_ms == 20
    assert projection.scenario_duration_ms == 25


def test_project_run_dedupes_duplicate_step_and_test_events() -> None:
    events = [
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.STEP_FINISHED,
            test_id="flaky_coin",
            step_id="coin_flip",
            status=StepStatus.SUCCESS,
            duration_ms=1,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.STEP_FINISHED,
            test_id="flaky_coin",
            step_id="coin_flip",
            status=StepStatus.SUCCESS,
            duration_ms=2,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.TEST_FINISHED,
            test_id="flaky_coin",
            duration_ms=1,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.TEST_FINISHED,
            test_id="flaky_coin",
            duration_ms=2,
            timestamp=datetime.now(UTC),
        ),
    ]

    projection = project_run(events)

    assert len(projection.steps) == 1
    assert projection.steps[0].duration_ms == 2
    assert len(projection.tests) == 1
    assert projection.tests[0].duration_ms == 2


def test_project_run_attributes_null_step_test_id_from_test_started() -> None:
    """Older executor wiped ContextVar test_id; TEST_STARTED still marks the owner."""
    events = [
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.TEST_STARTED,
            test_id="google_title",
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.STEP_FINISHED,
            test_id=None,
            step_id="open_page",
            status=StepStatus.SUCCESS,
            duration_ms=10,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.TEST_FINISHED,
            test_id="google_title",
            duration_ms=10,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.TEST_STARTED,
            test_id="youtube_ai_engineer_latest",
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.STEP_FINISHED,
            test_id=None,
            step_id="fetch_channel_feed",
            status=StepStatus.SUCCESS,
            duration_ms=20,
            timestamp=datetime.now(UTC),
        ),
        TestRunEvent(
            run_id="r1",
            event_type=TestRunEventType.TEST_FINISHED,
            test_id="youtube_ai_engineer_latest",
            duration_ms=20,
            timestamp=datetime.now(UTC),
        ),
    ]

    projection = project_run(events)

    assert [s.test_id for s in projection.steps] == [
        "google_title",
        "youtube_ai_engineer_latest",
    ]
    assert [t.test_id for t in projection.tests] == [
        "google_title",
        "youtube_ai_engineer_latest",
    ]
