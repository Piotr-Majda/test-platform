"""Google title steps — Given / When / Then."""

import pytest

from test_platform_executor.events import InMemoryProgressPublisher
from test_platform_executor.framework.adapters import FakePageFetcher
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import set_emission_context
from test_platform_executor.framework.google_steps import AssertTitleContainsStep, OpenGooglePageStep
from test_platform_executor.framework.steps import StepFailedError


@pytest.fixture(autouse=True)
def emission() -> InMemoryProgressPublisher:
    publisher = InMemoryProgressPublisher()
    set_emission_context(emitter=publisher.publish, run_id="run-1", test_id="google_title")
    return publisher


def test_open_page_stores_html() -> None:
    fetcher = FakePageFetcher({"https://www.google.com": "<html><title>Google</title></html>"})
    step = OpenGooglePageStep(fetcher)
    context = StepContext()

    step.execute(context)

    assert "<title>Google</title>" in context.get("page_html")


def test_assert_title_passes_when_expected_present() -> None:
    context = StepContext()
    context.set("page_html", "<html><title>Google</title></html>")
    step = AssertTitleContainsStep("Google")

    step.execute(context)

    assert context.get("page_title") == "Google"


def test_assert_title_fails_when_mismatch() -> None:
    context = StepContext()
    context.set("page_html", "<html><title>Other</title></html>")
    step = AssertTitleContainsStep("Google")

    with pytest.raises(StepFailedError):
        step.execute(context)
