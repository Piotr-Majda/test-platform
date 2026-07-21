"""@step decorator emits duration — Given / When / Then."""

import json
from pathlib import Path

import pytest
from test_platform_contracts import TestRunEventType

from test_platform_executor.events import InMemoryProgressPublisher
from test_platform_executor.framework.adapters import FakePageFetcher
from test_platform_executor.framework.artifacts import HtmlSnapshotArtifactStrategy, LocalArtifactStore
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import set_emission_context
from test_platform_executor.framework.google_steps import AssertTitleContainsStep, OpenGooglePageStep
from test_platform_executor.framework.scoped_log import ScopedLogger
from test_platform_executor.framework.steps import StepFailedError


def test_successful_step_emits_nested_step_log_json() -> None:
    publisher = InMemoryProgressPublisher()
    set_emission_context(emitter=publisher.publish, run_id="run-1", test_id="google_title")
    root = Path(__file__).resolve().parent / "_tmp_artifacts_success"
    root.mkdir(exist_ok=True)
    strategy = HtmlSnapshotArtifactStrategy(LocalArtifactStore(root, "run-1"))
    fetcher = FakePageFetcher({"https://www.google.com": "<html><title>Google</title></html>"})
    context = StepContext(log=ScopedLogger(test_id="google_title"))

    OpenGooglePageStep(fetcher, artifact_strategy=strategy).execute(context)

    finished = [e for e in publisher.events if e.event_type == TestRunEventType.STEP_FINISHED]
    assert len(finished) == 1
    names = {a.name for a in finished[0].artifacts}
    assert "step.log.json" in names
    assert "test.log.json" in names  # pass-path aggregated log for audit / false-positive checks

    step_log_path = root / "run-1" / "google_title" / "open_page" / "step.log.json"
    payload = json.loads(step_log_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["step_id"] == "open_page"
    assert payload["duration_ms"] >= 0
    assert payload["entries"][0]["layer"] == "domain"
    assert payload["entries"][0]["children"][0]["layer"] == "adapter"
    assert payload["entries"][0]["children"][0]["children"][0]["layer"] == "framework"

    test_log = json.loads(
        (root / "run-1" / "google_title" / "test.log.json").read_text(encoding="utf-8")
    )
    assert test_log["test_id"] == "google_title"
    assert test_log["steps"][0]["step_id"] == "open_page"


def test_failed_step_emits_html_snapshot_artifact() -> None:
    publisher = InMemoryProgressPublisher()
    set_emission_context(emitter=publisher.publish, run_id="run-2", test_id="google_title")
    root = Path(__file__).resolve().parent / "_tmp_artifacts"
    root.mkdir(exist_ok=True)
    store = LocalArtifactStore(root, "run-2")
    strategy = HtmlSnapshotArtifactStrategy(store)
    context = StepContext(log=ScopedLogger(test_id="google_title"))
    context.set("page_html", "<html><title>Nope</title></html>")
    context.set("page_url", "https://www.google.com")

    with pytest.raises(StepFailedError):
        AssertTitleContainsStep("Google", artifact_strategy=strategy).execute(context)

    failed = [e for e in publisher.events if e.event_type == TestRunEventType.STEP_FAILED]
    assert len(failed) == 1
    names = {a.name for a in failed[0].artifacts}
    assert "step.log.json" in names
    assert "test.log.json" in names
    assert "page.html" in names  # HTML snapshot only on failure
