"""Contract model tests — Given / When / Then."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from test_platform_contracts import (
    CONTRACTS_VERSION,
    AnalysisReport,
    AnalysisRequest,
    AnalysisScope,
    ArtifactKind,
    ArtifactRef,
    ErrorAnalysisItem,
    ExecuteTestCommand,
    FailureWhere,
    FlakinessSnapshot,
    PluginManifest,
    StepStatus,
    TestDefinition,
    TestRunEvent,
    TestRunEventType,
)


def test_contracts_version_is_semver() -> None:
    assert CONTRACTS_VERSION == "0.8.0"


def test_plugin_manifest_round_trips_json() -> None:
    # Given
    manifest = PluginManifest(
        plugin_id="example-executor",
        framework_version="0.1.0",
        contracts_version=CONTRACTS_VERSION,
        tests=[
            TestDefinition(
                id="google_title",
                name="Google page title",
                steps=["open_page", "assert_title"],
            )
        ],
    )

    # When
    restored = PluginManifest.model_validate_json(manifest.model_dump_json())

    # Then
    assert restored == manifest
    assert restored.model_dump(mode="json")["contracts_version"] == CONTRACTS_VERSION


def test_plugin_manifest_rejects_empty_plugin_id() -> None:
    with pytest.raises(ValidationError):
        PluginManifest(
            plugin_id="",
            framework_version="0.1.0",
            contracts_version=CONTRACTS_VERSION,
            tests=[],
        )


def test_plugin_manifest_rejects_empty_test_id() -> None:
    with pytest.raises(ValidationError):
        PluginManifest(
            plugin_id="example-executor",
            framework_version="0.1.0",
            contracts_version=CONTRACTS_VERSION,
            tests=[TestDefinition(id="", name="Broken", steps=[])],
        )


def test_test_definition_requires_id_and_name() -> None:
    payload = {"id": "google_title", "name": "Google page title", "steps": ["open_page", "assert_title"]}
    definition = TestDefinition.model_validate(payload)
    assert definition.id == "google_title"


def test_test_definition_rejects_empty_id() -> None:
    payload = {"id": "", "name": "Broken", "steps": []}
    with pytest.raises(ValidationError):
        TestDefinition.model_validate(payload)


def test_execute_test_command_round_trips_json() -> None:
    command = ExecuteTestCommand(
        run_id="run-1",
        scenario_id="scenario-1",
        test_ids=["google_title"],
        contracts_version=CONTRACTS_VERSION,
    )
    restored = ExecuteTestCommand.model_validate_json(command.model_dump_json())
    assert restored == command


def test_step_event_includes_duration_and_artifacts() -> None:
    event = TestRunEvent(
        run_id="run-1",
        event_type=TestRunEventType.STEP_FAILED,
        test_id="google_title",
        step_id="assert_title",
        status=StepStatus.FAILED,
        message="Title mismatch",
        error_trace="AssertionError",
        duration_ms=42,
        artifacts=[
            ArtifactRef(
                id="a1",
                kind=ArtifactKind.HTML_SNAPSHOT,
                name="page.html",
                content_type="text/html",
                relative_path="artifacts/run-1/page.html",
            )
        ],
        timestamp=datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
        contracts_version=CONTRACTS_VERSION,
    )
    payload = event.model_dump(mode="json")
    assert payload["duration_ms"] == 42
    assert payload["artifacts"][0]["kind"] == "html_snapshot"


def test_analysis_report_round_trips_json() -> None:
    report = AnalysisReport(
        id="an-1",
        scope=AnalysisScope.SCENARIO,
        scenario_id="sc-1",
        scenario_name="Smoke",
        sut_version="1.0.0",
        framework_version="0.1.0",
        infra="local",
        summary="Two shared failures across tests",
        errors=[
            ErrorAnalysisItem(
                fingerprint="abc123",
                label="TimeoutError: wait",
                description="Timeout while waiting for response",
                where=[FailureWhere(test_id="google_title", step_id="open_page")],
                occurrence_count=3,
                last_failure_run_id="run-9",
                sut_versions=["1.0.0"],
                framework_versions=["0.1.0"],
                given="SUT 1.0.0 · FW 0.1.0 · test google_title",
                when_steps=["open_page", "assert_title"],
                then_actual="Title mismatch",
                expected="Page title contains Google",
                root_cause_name="assertion drift",
                confidence_pct=72,
                error_type="assertion",
                components=["test", "step", "SUT"],
                reproduce_path="Run scenario Smoke; fail at open_page",
                likely_sut_issue=True,
                recommended_actions=["Check SUT latency", "Increase wait only if SUT OK"],
            )
        ],
        flakiness=[
            FlakinessSnapshot(
                test_id="google_title",
                sut_version="1.0.0",
                framework_version="0.1.0",
                total_runs=10,
                failed_runs=4,
                fail_rate=0.4,
                reliability="flaky",
            )
        ],
        generated_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        contracts_version=CONTRACTS_VERSION,
    )

    restored = AnalysisReport.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.errors[0].when_steps == ["open_page", "assert_title"]
    assert restored.errors[0].confidence_pct == 72


def test_analysis_request_requires_scope() -> None:
    req = AnalysisRequest(scope=AnalysisScope.RUN, run_id="run-1")
    assert req.scope == AnalysisScope.RUN
    assert req.run_id == "run-1"
