"""Flaky coin demo step — Given / When / Then."""

import pytest

from test_platform_contracts import TestRunEventType

from test_platform_executor.events import InMemoryProgressPublisher
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import set_emission_context
from test_platform_executor.framework.flaky_steps import CoinFlipStep
from test_platform_executor.framework.steps import StepFailedError


@pytest.fixture(autouse=True)
def emission() -> InMemoryProgressPublisher:
    publisher = InMemoryProgressPublisher()
    set_emission_context(emitter=publisher.publish, run_id="run-flake", test_id="flaky_coin")
    return publisher


def test_coin_flip_passes_when_probability_zero() -> None:
    step = CoinFlipStep(fail_probability=0.0)
    context = StepContext()

    step.execute(context)

    assert "coin_roll" in context.data


def test_coin_flip_fails_when_probability_one(emission: InMemoryProgressPublisher) -> None:
    step = CoinFlipStep(fail_probability=1.0)
    context = StepContext()

    with pytest.raises(StepFailedError, match="tails"):
        step.execute(context)

    failed = [e for e in emission.events if e.event_type == TestRunEventType.STEP_FAILED]
    assert len(failed) == 1
    assert failed[0].test_id == "flaky_coin"
    assert failed[0].step_id == "coin_flip"
