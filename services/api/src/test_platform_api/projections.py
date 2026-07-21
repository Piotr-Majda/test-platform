from pydantic import BaseModel, Field
from test_platform_contracts import ArtifactRef, TestRunEvent, TestRunEventType


class StepView(BaseModel):
    name: str
    status: str
    duration_ms: int | None = None
    test_id: str | None = None
    error_message: str | None = None
    error_trace: str | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)


class TestView(BaseModel):
    __test__ = False

    test_id: str
    status: str
    duration_ms: int | None = None


class RunProjection(BaseModel):
    steps: list[StepView]
    tests: list[TestView]
    scenario_duration_ms: int | None = None


def project_run(events: list[TestRunEvent]) -> RunProjection:
    """One row per step/test for a single execution (last event wins on duplicates)."""
    steps_by_key: dict[tuple[str | None, str], StepView] = {}
    step_order: list[tuple[str | None, str]] = []
    tests_by_id: dict[str, TestView] = {}
    test_order: list[str] = []
    scenario_duration_ms: int | None = None
    current_test_id: str | None = None
    # Steps seen since last TEST_STARTED (re-keyed when test_id was missing on emit)
    open_step_keys: list[tuple[str | None, str]] = []

    def _remember_step(key: tuple[str | None, str], view: StepView) -> None:
        if key not in steps_by_key:
            step_order.append(key)
            open_step_keys.append(key)
        steps_by_key[key] = view

    def _rekey_open_steps(test_id: str) -> None:
        """Assign buffered steps with null/empty test_id to the finished test."""
        nonlocal open_step_keys
        new_open: list[tuple[str | None, str]] = []
        for key in open_step_keys:
            view = steps_by_key.get(key)
            if view is None:
                continue
            if view.test_id:
                new_open.append(key)
                continue
            new_key = (test_id, key[1])
            del steps_by_key[key]
            view.test_id = test_id
            steps_by_key[new_key] = view
            # keep order: replace old key in step_order
            for i, ordered in enumerate(step_order):
                if ordered == key:
                    step_order[i] = new_key
                    break
            new_open.append(new_key)
        open_step_keys = new_open

    for event in events:
        if event.event_type == TestRunEventType.TEST_STARTED:
            current_test_id = event.test_id
            open_step_keys = []
        elif event.event_type in {TestRunEventType.STEP_FINISHED, TestRunEventType.STEP_FAILED}:
            failed = event.event_type == TestRunEventType.STEP_FAILED
            short = event.message.strip() if failed and event.message else None
            if short and len(short) > 80:
                short = short[:77] + "…"
            test_id = event.test_id or current_test_id
            key = (test_id, event.step_id or "unknown")
            view = StepView(
                name=event.step_id or "unknown",
                status=event.status.value if event.status else "unknown",
                duration_ms=event.duration_ms,
                test_id=test_id,
                error_message=short,
                error_trace=event.error_trace if failed else None,
                artifacts=list(event.artifacts),
            )
            _remember_step(key, view)
        elif event.event_type == TestRunEventType.TEST_FINISHED:
            test_id = event.test_id or current_test_id or "unknown"
            _rekey_open_steps(test_id)
            if test_id not in tests_by_id:
                test_order.append(test_id)
            tests_by_id[test_id] = TestView(
                test_id=test_id,
                status="success",
                duration_ms=event.duration_ms,
            )
            current_test_id = None
            open_step_keys = []
        elif event.event_type == TestRunEventType.TEST_FAILED:
            test_id = event.test_id or current_test_id or "unknown"
            _rekey_open_steps(test_id)
            if test_id not in tests_by_id:
                test_order.append(test_id)
            tests_by_id[test_id] = TestView(
                test_id=test_id,
                status="failed",
                duration_ms=event.duration_ms,
            )
            current_test_id = None
            open_step_keys = []
        elif event.event_type in {TestRunEventType.RUN_FINISHED, TestRunEventType.RUN_FAILED}:
            scenario_duration_ms = event.duration_ms

    return RunProjection(
        steps=[steps_by_key[k] for k in step_order if k in steps_by_key],
        tests=[tests_by_id[t] for t in test_order],
        scenario_duration_ms=scenario_duration_ms,
    )
