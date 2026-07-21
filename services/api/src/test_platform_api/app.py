import uuid
from collections.abc import Generator
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker
from test_platform_contracts import (
    CONTRACTS_VERSION,
    LOG_SCHEMA_VERSION,
    AnalysisReport,
    AnalysisRequest,
    ArtifactRetentionConfig,
    ExecuteTestCommand,
    HistoryConfig,
    PluginManifest,
    StepLogDocument,
    TestDefinition,
    TestLogDocument,
    TestRunEvent,
    TestRunEventType,
)

from test_platform_api.ai_analyzer import default_analyzer
from test_platform_api.analysis import FailureAnalyzer
from test_platform_api.analysis_export import build_analysis_export_zip
from test_platform_api.analysis_jobs import AnalysisJobStatus, AnalysisJobStore, start_analysis_job
from test_platform_api.artifact_prune import prune_scenario_artifacts
from test_platform_api.artifact_storage import artifact_storage
from test_platform_api.auth import (
    SESSION_COOKIE,
    AuthConfig,
    AuthManager,
    AuthUser,
    LoginRequest,
)
from test_platform_api.db import ScenarioRow, SqlAlchemyRepository
from test_platform_api.event_ingest import apply_event
from test_platform_api.history import (
    apply_occurrence_retention,
    compute_flakiness,
    compute_step_history,
    group_fingerprint_rows,
    scenario_duration_from_events,
    test_outcome_from_events,
)
from test_platform_api.logs import LogDocumentError, load_step_log, load_test_log
from test_platform_api.ports import EventPublisher
from test_platform_api.projections import RunProjection, project_run


class RunAnalysisBundle(BaseModel):
    """Latest run-level analysis plus newest per-test analyses for the run."""

    run: AnalysisReport | None = None
    tests: dict[str, AnalysisReport] = Field(default_factory=dict)


class CreateScenarioRequest(BaseModel):
    name: str = Field(min_length=1)
    test_ids: list[str] = Field(min_length=1)
    sut_version: str = "unknown"
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    artifacts: ArtifactRetentionConfig = Field(default_factory=ArtifactRetentionConfig)


class UpdateScenarioRequest(BaseModel):
    name: str | None = None
    test_ids: list[str] | None = None
    sut_version: str | None = None
    history: HistoryConfig | None = None
    artifacts: ArtifactRetentionConfig | None = None


class ScenarioResponse(BaseModel):
    id: str
    name: str
    test_ids: list[str]
    sut_version: str
    history: HistoryConfig
    artifacts: ArtifactRetentionConfig


class RunResponse(BaseModel):
    id: str
    scenario_id: str
    status: str
    sut_version: str
    framework_version: str


class RunDetailResponse(BaseModel):
    id: str
    scenario_id: str
    status: str
    sut_version: str
    framework_version: str
    duration_ms: int | None
    created_at: datetime
    events: list[TestRunEvent]
    projection: RunProjection


class HistoryRunItem(BaseModel):
    id: str
    status: str
    sut_version: str
    framework_version: str
    duration_ms: int | None
    created_at: datetime
    # test_id -> finished | failed (for per-test timelines)
    test_results: dict[str, str] = Field(default_factory=dict)


class DurationTrendItem(BaseModel):
    last_duration_ms: int | None
    previous_avg_ms: float | None
    delta_ms: int | None
    direction: str


class StepHistoryItem(BaseModel):
    step_id: str
    total: int
    failed: int
    fail_rate: float
    avg_duration_ms: float | None
    trend: DurationTrendItem
    reliability: str = "unknown"


class FlakinessItem(BaseModel):
    test_id: str
    sut_version: str
    framework_version: str
    total_runs: int
    failed_runs: int
    fail_rate: float
    avg_duration_ms: float | None
    min_duration_ms: int | None
    max_duration_ms: int | None
    trend: DurationTrendItem
    reliability: str = "unknown"
    steps: list[StepHistoryItem] = Field(default_factory=list)


class FailureOccurrenceItem(BaseModel):
    run_id: str
    test_id: str
    step_id: str
    message: str
    created_at: datetime


class FingerprintItem(BaseModel):
    fingerprint: str
    label: str
    step_id: str
    test_id: str
    sut_version: str
    framework_version: str
    count: int
    recent_failures: list[FailureOccurrenceItem]
    timeline: list[FailureOccurrenceItem] = Field(default_factory=list)


class ScenarioHistoryResponse(BaseModel):
    scenario_id: str
    runs: list[HistoryRunItem]
    flakiness: list[FlakinessItem]
    fingerprints: list[FingerprintItem] = Field(default_factory=list)


def _scenario_response(row: ScenarioRow) -> ScenarioResponse:
    return ScenarioResponse(
        id=row.id,
        name=row.name,
        test_ids=[t for t in row.test_ids_csv.split(",") if t],
        sut_version=row.sut_version,
        history=HistoryConfig(
            max_runs=row.history_max_runs,
            max_days=row.history_max_days,
        ),
        artifacts=ArtifactRetentionConfig(
            max_runs=row.artifact_max_runs,
            max_days=row.artifact_max_days,
            keep_at_least_one_failed=bool(row.artifact_keep_failed_only),
        ),
    )


def create_app(
    session_factory: sessionmaker[Session],
    publisher: EventPublisher,
    analyzer: FailureAnalyzer | None = None,
    auth_config: AuthConfig | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Test Platform API",
        version="0.7.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json"
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.session_factory = session_factory
    app.state.publisher = publisher
    app.state.analyzer = analyzer or default_analyzer()
    app.state.analysis_jobs = AnalysisJobStore()
    app.state.auth = AuthManager(auth_config or AuthConfig.disabled())

    @app.middleware("http")
    async def authorize_request(request: Request, call_next):
        auth: AuthManager = app.state.auth
        if not auth.config.enabled:
            return await call_next(request)

        path = request.url.path
        if request.method == "OPTIONS" or path in {"/health", "/auth/login", "/auth/logout"}:
            return await call_next(request)

        # These callbacks are reachable only through Railway's private network;
        # nginx explicitly blocks them on the public web service.
        is_executor_callback = path == "/plugins/manifest" or (
            path.startswith("/runs/") and path.endswith("/events")
        )
        if is_executor_callback:
            return await call_next(request)

        user = auth.read_session(request.cookies.get(SESSION_COOKIE))
        if user is None:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        request.state.user = user

        admin_only = (
            (request.method == "POST" and path == "/scenarios")
            or (request.method in {"PATCH", "DELETE"} and path.startswith("/scenarios/"))
        )
        if admin_only and user.role != "admin":
            return JSONResponse({"detail": "Admin role required"}, status_code=403)
        return await call_next(request)

    def get_repo() -> Generator[SqlAlchemyRepository, None, None]:
        session = app.state.session_factory()
        try:
            yield SqlAlchemyRepository(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/login", response_model=AuthUser)
    def login(body: LoginRequest, response: Response) -> AuthUser:
        auth: AuthManager = app.state.auth
        user = auth.authenticate(body.username, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        response.set_cookie(
            SESSION_COOKIE,
            auth.create_session(user),
            max_age=auth.config.session_ttl_seconds,
            httponly=True,
            secure=auth.config.secure_cookie,
            samesite="lax",
            path="/",
        )
        return user

    @app.post("/auth/logout", status_code=204)
    def logout(response: Response) -> None:
        response.delete_cookie(SESSION_COOKIE, path="/")

    @app.get("/auth/me", response_model=AuthUser)
    def current_user(request: Request) -> AuthUser:
        return request.state.user

    @app.post("/plugins/manifest", status_code=204)
    def register_plugin_manifest(
        body: PluginManifest,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> None:
        if body.contracts_version != CONTRACTS_VERSION:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"contracts_version mismatch: plugin={body.contracts_version!r} "
                    f"platform={CONTRACTS_VERSION!r}"
                ),
            )
        if body.log_schema_version != LOG_SCHEMA_VERSION:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"log_schema_version mismatch: plugin={body.log_schema_version!r} "
                    f"platform={LOG_SCHEMA_VERSION!r}"
                ),
            )
        repo.upsert_plugin(body.plugin_id, body.framework_version)
        repo.replace_plugin_catalog(body.plugin_id, body.tests)

    @app.get("/tests", response_model=list[TestDefinition])
    def list_tests(repo: SqlAlchemyRepository = Depends(get_repo)) -> list[TestDefinition]:
        return repo.list_tests()

    @app.post("/scenarios", response_model=ScenarioResponse, status_code=201)
    def create_scenario(
        body: CreateScenarioRequest,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> ScenarioResponse:
        scenario_id = str(uuid.uuid4())
        repo.create_scenario(
            scenario_id,
            body.name,
            body.test_ids,
            sut_version=body.sut_version,
            history_max_runs=body.history.max_runs,
            history_max_days=body.history.max_days,
            artifact_max_runs=body.artifacts.max_runs,
            artifact_max_days=body.artifacts.max_days,
            artifact_keep_failed_only=body.artifacts.keep_at_least_one_failed,
        )
        row = repo.get_scenario(scenario_id)
        assert row is not None
        return _scenario_response(row)

    @app.get("/scenarios", response_model=list[ScenarioResponse])
    def list_scenarios(repo: SqlAlchemyRepository = Depends(get_repo)) -> list[ScenarioResponse]:
        return [_scenario_response(row) for row in repo.list_scenarios()]

    @app.patch("/scenarios/{scenario_id}", response_model=ScenarioResponse)
    def update_scenario(
        scenario_id: str,
        body: UpdateScenarioRequest,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> ScenarioResponse:
        kwargs: dict = {}
        if body.name is not None:
            kwargs["name"] = body.name
        if body.test_ids is not None:
            kwargs["test_ids"] = body.test_ids
        if body.sut_version is not None:
            kwargs["sut_version"] = body.sut_version
        if body.history is not None:
            kwargs["history_max_runs"] = body.history.max_runs
            kwargs["history_max_days"] = body.history.max_days
        if body.artifacts is not None:
            kwargs["artifact_max_runs"] = body.artifacts.max_runs
            kwargs["artifact_max_days"] = body.artifacts.max_days
            kwargs["artifact_keep_failed_only"] = body.artifacts.keep_at_least_one_failed
        row = repo.update_scenario(scenario_id, **kwargs)
        if row is None:
            raise HTTPException(status_code=404, detail="scenario not found")
        if body.artifacts is not None:
            prune_scenario_artifacts(
                repo,
                scenario_id,
                max_runs=row.artifact_max_runs,
                max_days=row.artifact_max_days,
                keep_at_least_one_failed=bool(row.artifact_keep_failed_only),
                history_max_runs=row.history_max_runs,
                history_max_days=row.history_max_days,
            )
        return _scenario_response(row)

    @app.delete("/scenarios/{scenario_id}", status_code=204)
    def delete_scenario(
        scenario_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> None:
        deleted = repo.delete_scenario(scenario_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="scenario not found")

    @app.post("/scenarios/{scenario_id}/runs", response_model=RunResponse, status_code=201)
    def start_run(
        scenario_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> RunResponse:
        scenario = repo.get_scenario(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="scenario not found")

        test_ids = [t for t in scenario.test_ids_csv.split(",") if t]
        plugin_id = repo.plugin_id_for_test(test_ids[0]) if test_ids else "default"
        framework_version = repo.get_plugin_version(plugin_id)
        sut_version = scenario.sut_version

        run_id = str(uuid.uuid4())
        repo.create_run(
            run_id,
            scenario_id,
            sut_version=sut_version,
            framework_version=framework_version,
        )
        repo.update_run_status(run_id, "queued")
        repo.prune_scenario_history(
            scenario_id,
            max_runs=scenario.history_max_runs,
            max_days=scenario.history_max_days,
        )
        prune_scenario_artifacts(
            repo,
            scenario_id,
            max_runs=scenario.artifact_max_runs,
            max_days=scenario.artifact_max_days,
            keep_at_least_one_failed=bool(scenario.artifact_keep_failed_only),
            history_max_runs=scenario.history_max_runs,
            history_max_days=scenario.history_max_days,
        )

        command = ExecuteTestCommand(
            run_id=run_id,
            scenario_id=scenario_id,
            test_ids=test_ids,
            sut_version=sut_version,
            framework_version=framework_version,
        )
        app.state.publisher.publish_execute(command)
        return RunResponse(
            id=run_id,
            scenario_id=scenario_id,
            status="queued",
            sut_version=sut_version,
            framework_version=framework_version,
        )

    @app.get("/scenarios/{scenario_id}/history", response_model=ScenarioHistoryResponse)
    def scenario_history(
        scenario_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> ScenarioHistoryResponse:
        scenario = repo.get_scenario(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="scenario not found")

        runs = repo.list_runs_for_scenario(scenario_id)
        test_ids = [t for t in scenario.test_ids_csv.split(",") if t]
        # newest-first samples per flakiness key
        buckets: dict[tuple[str, str, str], list[tuple[str, int | None]]] = {}
        step_buckets: dict[tuple[str, str, str], dict[str, list[tuple[str, int | None]]]] = {}
        history_runs: list[HistoryRunItem] = []

        for run in runs:
            events = repo.list_events(run.id)
            duration_ms = run.duration_ms
            if duration_ms is None:
                duration_ms = scenario_duration_from_events(events)

            test_results: dict[str, str] = {}
            for test_id in test_ids:
                status, _duration = test_outcome_from_events(events, test_id)
                if status is None:
                    if run.status in {"finished", "failed"} and len(test_ids) == 1:
                        status = run.status
                    else:
                        continue
                # Normalize for UI: finished → passed semantics on timeline
                test_results[test_id] = "failed" if status == "failed" else "finished"

            history_runs.append(
                HistoryRunItem(
                    id=run.id,
                    status=run.status,
                    sut_version=run.sut_version,
                    framework_version=run.framework_version,
                    duration_ms=duration_ms,
                    created_at=run.created_at,
                    test_results=test_results,
                )
            )

            run_test_ids = {
                e.test_id
                for e in events
                if e.test_id
                and e.event_type
                in {TestRunEventType.TEST_FINISHED, TestRunEventType.TEST_FAILED}
            }
            fallback_test_id = next(iter(run_test_ids), None)

            for test_id in test_ids:
                status, duration = test_outcome_from_events(events, test_id)
                if status is None:
                    if run.status in {"finished", "failed"} and len(test_ids) == 1:
                        status = run.status
                        duration = duration_ms
                    else:
                        continue
                key = (test_id, run.sut_version, run.framework_version)
                buckets.setdefault(key, []).append((status, duration))

            for event in events:
                if event.event_type not in {
                    TestRunEventType.STEP_FINISHED,
                    TestRunEventType.STEP_FAILED,
                }:
                    continue
                step_id = event.step_id or "unknown"
                test_id = event.test_id or fallback_test_id
                if test_id is None or test_id not in test_ids:
                    continue
                key = (test_id, run.sut_version, run.framework_version)
                step_status = "failed" if event.event_type == TestRunEventType.STEP_FAILED else "finished"
                step_buckets.setdefault(key, {}).setdefault(step_id, []).append(
                    (step_status, event.duration_ms)
                )

        flakiness: list[FlakinessItem] = []
        for (test_id, sut, fw), samples in buckets.items():
            stats = compute_flakiness(
                samples,
                test_id=test_id,
                sut_version=sut,
                framework_version=fw,
            )
            steps = compute_step_history(step_buckets.get((test_id, sut, fw), {}))
            flakiness.append(
                FlakinessItem(
                    test_id=stats.test_id,
                    sut_version=stats.sut_version,
                    framework_version=stats.framework_version,
                    total_runs=stats.total_runs,
                    failed_runs=stats.failed_runs,
                    fail_rate=stats.fail_rate,
                    avg_duration_ms=stats.avg_duration_ms,
                    min_duration_ms=stats.min_duration_ms,
                    max_duration_ms=stats.max_duration_ms,
                    trend=DurationTrendItem(
                        last_duration_ms=stats.trend.last_duration_ms,
                        previous_avg_ms=stats.trend.previous_avg_ms,
                        delta_ms=stats.trend.delta_ms,
                        direction=stats.trend.direction,
                    ),
                    reliability=stats.reliability,
                    steps=[
                        StepHistoryItem(
                            step_id=s.step_id,
                            total=s.total,
                            failed=s.failed,
                            fail_rate=s.fail_rate,
                            avg_duration_ms=s.avg_duration_ms,
                            trend=DurationTrendItem(
                                last_duration_ms=s.trend.last_duration_ms,
                                previous_avg_ms=s.trend.previous_avg_ms,
                                delta_ms=s.trend.delta_ms,
                                direction=s.trend.direction,
                            ),
                            reliability=s.reliability,
                        )
                        for s in steps
                    ],
                )
            )

        # Persisted occurrences survive run prune; timeline uses same retention as run history
        occurrence_rows = repo.list_fingerprint_occurrences(scenario_id)
        fingerprint_rows = [
            (
                row.run_id,
                row.test_id,
                row.step_id,
                row.sut_version,
                row.framework_version,
                row.fingerprint,
                row.label,
                row.message,
                row.created_at,
            )
            for row in occurrence_rows
        ]
        windowed_rows = apply_occurrence_retention(
            fingerprint_rows,
            created_at_of=lambda r: r[8],
            run_id_of=lambda r: r[0],
            max_runs=scenario.history_max_runs,
            max_days=scenario.history_max_days,
        )
        timeline_by_key = {
            (g.fingerprint, g.sut_version, g.framework_version, g.test_id, g.step_id): g.occurrences
            for g in group_fingerprint_rows(windowed_rows)
        }
        fingerprints = [
            FingerprintItem(
                fingerprint=g.fingerprint,
                label=g.label,
                step_id=g.step_id,
                test_id=g.test_id,
                sut_version=g.sut_version,
                framework_version=g.framework_version,
                count=g.count,
                recent_failures=[
                    FailureOccurrenceItem(
                        run_id=o.run_id,
                        test_id=o.test_id,
                        step_id=o.step_id,
                        message=o.message,
                        created_at=o.created_at,
                    )
                    for o in g.recent_failures
                ],
                timeline=[
                    FailureOccurrenceItem(
                        run_id=o.run_id,
                        test_id=o.test_id,
                        step_id=o.step_id,
                        message=o.message,
                        created_at=o.created_at,
                    )
                    for o in timeline_by_key.get(
                        (g.fingerprint, g.sut_version, g.framework_version, g.test_id, g.step_id),
                        [],
                    )
                ],
            )
            for g in group_fingerprint_rows(fingerprint_rows)
        ]

        return ScenarioHistoryResponse(
            scenario_id=scenario_id,
            runs=history_runs,
            flakiness=flakiness,
            fingerprints=fingerprints,
        )

    @app.get("/runs/{run_id}", response_model=RunDetailResponse)
    def get_run(
        run_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> RunDetailResponse:
        run = repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        events = repo.list_events(run_id)
        duration_ms = run.duration_ms
        if duration_ms is None:
            duration_ms = scenario_duration_from_events(events)
        return RunDetailResponse(
            id=run.id,
            scenario_id=run.scenario_id,
            status=run.status,
            sut_version=run.sut_version,
            framework_version=run.framework_version,
            duration_ms=duration_ms,
            created_at=run.created_at,
            events=events,
            projection=project_run(events),
        )

    @app.get("/runs/{run_id}/tests/{test_id}/logs", response_model=TestLogDocument)
    def get_test_logs(
        run_id: str,
        test_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> TestLogDocument:
        if repo.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            document = load_test_log(
                artifact_storage(),
                run_id=run_id,
                test_id=test_id,
                events=repo.list_events(run_id),
            )
        except LogDocumentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if document is None:
            raise HTTPException(status_code=404, detail="test logs not found")
        return document

    @app.get(
        "/runs/{run_id}/tests/{test_id}/steps/{step_id}/logs",
        response_model=StepLogDocument,
    )
    def get_step_logs(
        run_id: str,
        test_id: str,
        step_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> StepLogDocument:
        if repo.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            document = load_step_log(
                artifact_storage(),
                run_id=run_id,
                test_id=test_id,
                step_id=step_id,
                events=repo.list_events(run_id),
            )
        except LogDocumentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if document is None:
            raise HTTPException(status_code=404, detail="step logs not found")
        return document

    @app.post("/runs/{run_id}/events", status_code=204)
    def ingest_event(
        run_id: str,
        event: TestRunEvent,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> None:
        if event.run_id != run_id:
            raise HTTPException(status_code=400, detail="run_id mismatch")
        run = repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        apply_event(repo, event)

    @app.get("/runs/{run_id}/analysis", response_model=RunAnalysisBundle)
    def get_run_analysis(
        run_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> RunAnalysisBundle:
        run = repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        run_report = repo.find_latest_analysis(run_id=run_id, scope="run")
        tests = {r.test_id: r for r in repo.list_test_analyses_for_run(run_id) if r.test_id}
        # Hydrate from run report refs when column/index lookup missed children
        if run_report and run_report.test_analyses:
            for ref in run_report.test_analyses:
                if ref.test_id and ref.test_id not in tests:
                    child = repo.get_analysis_report(ref.analysis_id)
                    if child is not None:
                        tests[ref.test_id] = child
        return RunAnalysisBundle(run=run_report, tests=tests)

    @app.get("/runs/{run_id}/tests/{test_id}/analysis", response_model=AnalysisReport)
    def get_test_analysis(
        run_id: str,
        test_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> AnalysisReport:
        run = repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        report = repo.find_latest_analysis(run_id=run_id, scope="test", test_id=test_id)
        if report is None:
            # Fall back via parent run report refs
            run_report = repo.find_latest_analysis(run_id=run_id, scope="run")
            if run_report:
                for ref in run_report.test_analyses:
                    if ref.test_id == test_id:
                        report = repo.get_analysis_report(ref.analysis_id)
                        break
        if report is None:
            raise HTTPException(status_code=404, detail="test analysis not found")
        return report

    @app.post("/analyses", response_model=AnalysisJobStatus, status_code=202)
    def create_analysis(body: AnalysisRequest) -> AnalysisJobStatus:
        """Start analysis in a background thread; poll GET /analyses/jobs/{id} until done."""
        from test_platform_api.analysis import validate_analysis_request

        try:
            validate_analysis_request(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return start_analysis_job(
            store=app.state.analysis_jobs,
            session_factory=app.state.session_factory,
            analyzer=app.state.analyzer,
            request=body,
        )

    @app.get("/analyses/jobs/{job_id}", response_model=AnalysisJobStatus)
    def get_analysis_job(job_id: str) -> AnalysisJobStatus:
        job = app.state.analysis_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="analysis job not found")
        return job

    @app.get("/analyses/{analysis_id}", response_model=AnalysisReport)
    def get_analysis(
        analysis_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> AnalysisReport:
        report = repo.get_analysis_report(analysis_id)
        if report is None:
            raise HTTPException(status_code=404, detail="analysis not found")
        return report

    @app.get("/analyses/{analysis_id}/export")
    def export_analysis(
        analysis_id: str,
        repo: SqlAlchemyRepository = Depends(get_repo),
    ) -> StreamingResponse:
        """ZIP: report.md + report.json + artifacts from related failure runs."""
        report = repo.get_analysis_report(analysis_id)
        if report is None:
            raise HTTPException(status_code=404, detail="analysis not found")
        payload = build_analysis_export_zip(report)
        filename = f"analysis-{analysis_id[:8]}.zip"
        return StreamingResponse(
            iter([payload]),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/artifacts/{relative_path:path}")
    def get_artifact(relative_path: str) -> Response:
        try:
            payload = artifact_storage().read_bytes(relative_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid artifact path") from exc
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail=f"artifact not found: {relative_path}",
            )
        # JSON logs: return inline JSON (fetch-friendly). Other files: downloadable.
        if relative_path.lower().endswith(".json"):
            return Response(
                content=payload,
                media_type="application/json",
                headers={"Cache-Control": "no-store"},
            )
        filename = relative_path.replace("\\", "/").rsplit("/", 1)[-1]
        return Response(
            content=payload,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app
