import pytest

from test_platform_executor.framework.artifacts import HtmlSnapshotArtifactStrategy, LocalArtifactStore
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import get_run_id, get_test_id
from test_platform_executor.framework.flaky_steps import CoinFlipStep
from test_platform_executor.framework.scoped_log import ScopedLogger
from test_platform_executor.paths import artifacts_dir


@pytest.mark.platform_test("flaky_coin")
def test_flaky_coin(platform_emitter) -> None:
    store = LocalArtifactStore(artifacts_dir(), get_run_id())
    strategy = HtmlSnapshotArtifactStrategy(store)
    context = StepContext(log=ScopedLogger(test_id=get_test_id()))
    CoinFlipStep(artifact_strategy=strategy).execute(context)
