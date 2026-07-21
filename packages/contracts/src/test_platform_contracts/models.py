from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

CONTRACTS_VERSION = "0.8.0"
LOG_SCHEMA_VERSION = "1.0"


class StepStatus(StrEnum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TestRunEventType(StrEnum):
    __test__ = False

    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    TEST_STARTED = "test_started"
    TEST_FINISHED = "test_finished"
    TEST_FAILED = "test_failed"
    STEP_FINISHED = "step_finished"
    STEP_FAILED = "step_failed"
    LOG = "log"
    INFRA_ERROR = "infra_error"
    ARTIFACT = "artifact"


class ArtifactKind(StrEnum):
    LOG = "log"
    HTML_SNAPSHOT = "html_snapshot"
    SCREENSHOT = "screenshot"
    OTHER = "other"


class ArtifactRef(BaseModel):
    id: str = Field(min_length=1)
    kind: ArtifactKind
    name: str = Field(min_length=1)
    content_type: str = "application/octet-stream"
    relative_path: str = Field(min_length=1)


class StructuredLogEntry(BaseModel):
    """Framework-neutral log entry produced by plugins and rendered by the platform."""

    timestamp: datetime
    layer: str = Field(min_length=1)
    message: str = Field(min_length=1)
    component: str | None = None
    level: str = "info"
    duration_ms: int | None = Field(default=None, ge=0)
    event: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    children: list["StructuredLogEntry"] = Field(default_factory=list)


class StepLogDocument(BaseModel):
    schema_version: str = LOG_SCHEMA_VERSION
    scope: Literal["step"] = "step"
    test_id: str | None = None
    step_id: str = Field(min_length=1)
    status: str
    duration_ms: int | None = Field(default=None, ge=0)
    entries: list[StructuredLogEntry] = Field(default_factory=list)


class TestLogDocument(BaseModel):
    __test__ = False

    schema_version: str = LOG_SCHEMA_VERSION
    scope: Literal["test"] = "test"
    test_id: str = Field(min_length=1)
    steps: list[StepLogDocument] = Field(default_factory=list)


class TestDefinition(BaseModel):
    __test__ = False

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    steps: list[str] = Field(default_factory=list)


class PluginManifest(BaseModel):
    """Framework → platform handshake: identity, contract version, discovered tests."""

    plugin_id: str = Field(min_length=1)
    framework_version: str = Field(min_length=1)
    contracts_version: str = CONTRACTS_VERSION
    log_schema_version: str = LOG_SCHEMA_VERSION
    tests: list[TestDefinition] = Field(default_factory=list)


class HistoryConfig(BaseModel):
    """Run history retention: keep runs in last max_days ∩ last max_runs."""

    max_runs: int | None = Field(default=50, ge=1)
    max_days: int | None = Field(default=None, ge=1)


class ArtifactRetentionConfig(BaseModel):
    """
    Disk artifact retention (independent of run history retention).

    Keeps artifacts for the last max_runs ∩ max_days. When keep_at_least_one_failed
    is true, also retains the newest failed run that still falls inside the
    scenario history window (even if it is older than the artifact max_runs slot).
    """

    max_runs: int | None = Field(default=20, ge=1)
    max_days: int | None = Field(default=None, ge=1)
    keep_at_least_one_failed: bool = True


class Scenario(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    test_ids: list[str] = Field(default_factory=list)
    sut_version: str = "unknown"
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    artifacts: ArtifactRetentionConfig = Field(default_factory=ArtifactRetentionConfig)

    @field_validator("test_ids")
    @classmethod
    def test_ids_must_be_non_empty_strings(cls, value: list[str]) -> list[str]:
        for test_id in value:
            if not test_id:
                raise ValueError("test_ids must not contain empty strings")
        return value


class ExecuteTestCommand(BaseModel):
    run_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    test_ids: list[str] = Field(min_length=1)
    sut_version: str = "unknown"
    framework_version: str = "unknown"
    contracts_version: str = CONTRACTS_VERSION


class TestRunEvent(BaseModel):
    __test__ = False

    run_id: str = Field(min_length=1)
    event_type: TestRunEventType
    test_id: str | None = None
    step_id: str | None = None
    status: StepStatus | None = None
    message: str = ""
    error_trace: str | None = None
    duration_ms: int | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    timestamp: datetime
    contracts_version: str = CONTRACTS_VERSION


class AnalysisScope(StrEnum):
    RUN = "run"
    TEST = "test"
    FINGERPRINT = "fingerprint"
    SCENARIO = "scenario"


class AnalysisRequest(BaseModel):
    """Manual analysis trigger — exactly one scope target is required."""

    scope: AnalysisScope
    scenario_id: str | None = None
    run_id: str | None = None
    test_id: str | None = None
    fingerprint: str | None = None

    @field_validator("scenario_id", "run_id", "test_id", "fingerprint")
    @classmethod
    def empty_string_to_none(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value


class FailureWhere(BaseModel):
    test_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)


class HealthSignal(BaseModel):
    """Pass-path / false-positive checks (missing logs, empty logs, size drift)."""

    test_id: str = Field(min_length=1)
    kind: str  # missing_log | empty_log | log_size_anomaly
    severity: str = "warn"  # info | warn
    message: str = ""
    current_bytes: int | None = None
    baseline_median_bytes: int | None = None


class TestAnalysisRef(BaseModel):
    """Pointer from a run-level report to a per-test analysis."""

    test_id: str = Field(min_length=1)
    analysis_id: str = Field(min_length=1)
    summary: str = ""
    health_signal_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)


class ErrorAnalysisItem(BaseModel):
    fingerprint: str = Field(min_length=1)
    label: str = ""
    description: str = ""
    where: list[FailureWhere] = Field(default_factory=list)
    occurrence_count: int = Field(default=0, ge=0)
    last_failure_run_id: str | None = None
    sut_versions: list[str] = Field(default_factory=list)
    framework_versions: list[str] = Field(default_factory=list)
    # GWT-style failure narrative (step path + context)
    given: str = ""
    when_steps: list[str] = Field(default_factory=list)
    then_actual: str = ""
    expected: str = ""
    root_cause_name: str = ""
    confidence_pct: int = Field(default=0, ge=0, le=100)
    error_type: str = "unknown"  # flake | assertion | timeout | infra | unknown
    components: list[str] = Field(default_factory=list)
    reproduce_path: str = ""
    likely_sut_issue: bool = False
    recommended_actions: list[str] = Field(default_factory=list)


class FlakinessSnapshot(BaseModel):
    """Copied from scenario history metrics — not invented by the LLM."""

    test_id: str = Field(min_length=1)
    sut_version: str = "unknown"
    framework_version: str = "unknown"
    total_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    fail_rate: float = Field(ge=0.0, le=1.0)
    reliability: str = "unknown"


class AnalysisReport(BaseModel):
    id: str = Field(min_length=1)
    scope: AnalysisScope
    scenario_id: str | None = None
    scenario_name: str = ""
    run_id: str | None = None
    test_id: str | None = None
    fingerprint: str | None = None
    parent_analysis_id: str | None = None
    sut_version: str = "unknown"
    framework_version: str = "unknown"
    infra: str = "local"
    summary: str = ""
    scenario_reliability: str = "unknown"  # stable | watch | flaky | unknown
    errors: list[ErrorAnalysisItem] = Field(default_factory=list)
    flakiness: list[FlakinessSnapshot] = Field(default_factory=list)
    health_signals: list[HealthSignal] = Field(default_factory=list)
    test_analyses: list[TestAnalysisRef] = Field(default_factory=list)
    generated_at: datetime
    contracts_version: str = CONTRACTS_VERSION
