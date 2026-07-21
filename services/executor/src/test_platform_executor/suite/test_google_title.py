import os

import pytest

from test_platform_executor.framework.adapters import FakePageFetcher, HttpxPageFetcher
from test_platform_executor.framework.artifacts import HtmlSnapshotArtifactStrategy, create_artifact_store
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import get_run_id, get_test_id
from test_platform_executor.framework.google_steps import AssertTitleContainsStep, OpenGooglePageStep
from test_platform_executor.framework.scoped_log import ScopedLogger
from test_platform_executor.paths import artifacts_dir


def _page_fetcher():
    fake_html = os.getenv("PLATFORM_FAKE_HTML")
    if fake_html is not None:
        return FakePageFetcher({"https://www.google.com": fake_html})
    return HttpxPageFetcher()


@pytest.mark.platform_test("google_title")
def test_google_title(platform_emitter) -> None:
    store = create_artifact_store(artifacts_dir(), get_run_id())
    strategy = HtmlSnapshotArtifactStrategy(store)
    context = StepContext(log=ScopedLogger(test_id=get_test_id()))

    OpenGooglePageStep(_page_fetcher(), artifact_strategy=strategy).execute(context)
    AssertTitleContainsStep("Google", artifact_strategy=strategy).execute(context)
