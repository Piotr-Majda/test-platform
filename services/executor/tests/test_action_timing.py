"""Step duration measures SUT action time only — Given / When / Then."""

import time

from test_platform_contracts import TestRunEventType

from test_platform_executor.events import InMemoryProgressPublisher
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import (
    set_emission_context,
    take_test_action_ms,
)
from test_platform_executor.framework.step_decorator import step


@step("slow_framework_fast_action")
class SlowFrameworkFastActionStep:
    def execute(self, context: StepContext) -> None:
        time.sleep(0.05)  # framework / logging overhead — must NOT count
        with context.timed_action():
            time.sleep(0.01)  # SUT-facing work — must count
        time.sleep(0.05)  # emit / artifact path — must NOT count


def test_step_duration_excludes_framework_overhead() -> None:
    publisher = InMemoryProgressPublisher()
    set_emission_context(emitter=publisher.publish, run_id="run-timing")
    context = StepContext()

    SlowFrameworkFastActionStep().execute(context)

    finished = [e for e in publisher.events if e.event_type == TestRunEventType.STEP_FINISHED]
    assert len(finished) == 1
    # ~10ms action; wall clock was ~110ms — keep a clear gap
    assert finished[0].duration_ms is not None
    assert 5 <= finished[0].duration_ms <= 40
    assert take_test_action_ms() == finished[0].duration_ms
