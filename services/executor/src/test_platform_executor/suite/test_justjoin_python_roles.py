import os

import pytest

from test_platform_executor.framework.artifacts import HtmlSnapshotArtifactStrategy, LocalArtifactStore
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import get_run_id, get_test_id
from test_platform_executor.framework.justjoin_client import (
    FakeJustJoinOffersClient,
    HttpxJustJoinOffersClient,
    offer_url_from_slug,
)
from test_platform_executor.framework.justjoin_steps import (
    AssertOfferUrlsStep,
    ExtractPythonRolesStep,
    FetchPythonOffersStep,
)
from test_platform_executor.framework.scoped_log import ScopedLogger
from test_platform_executor.paths import artifacts_dir


def _client():
    """Unit/CI can set PLATFORM_FAKE_JJIT=1; platform E2E uses the live API."""
    if os.getenv("PLATFORM_FAKE_JJIT") == "1":
        offers = [
            {
                "title": f"Python Developer {i}",
                "slug": f"acme-python-developer-{i}--warszawa-python",
            }
            for i in range(10)
        ]
        statuses = {offer_url_from_slug(o["slug"]): 200 for o in offers[:3]}
        return FakeJustJoinOffersClient(offers=offers, url_status=statuses)
    return HttpxJustJoinOffersClient()


@pytest.mark.platform_test("justjoin_python_roles")
def test_justjoin_python_roles(platform_emitter) -> None:
    store = LocalArtifactStore(artifacts_dir(), get_run_id())
    strategy = HtmlSnapshotArtifactStrategy(store)
    client = _client()
    context = StepContext(log=ScopedLogger(test_id=get_test_id()))

    FetchPythonOffersStep(client, artifact_strategy=strategy).execute(context)
    ExtractPythonRolesStep(limit=10, artifact_strategy=strategy).execute(context)
    AssertOfferUrlsStep(client, check_count=3, artifact_strategy=strategy).execute(context)
