from collections.abc import Generator
from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, MetaData, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

from test_platform_contracts import (
    AnalysisReport,
    ArtifactRef,
    StepStatus,
    TestDefinition,
    TestRunEvent,
    TestRunEventType,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base — tables live in the default schema (Postgres `public`)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class PluginRow(Base):
    __tablename__ = "plugins"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    framework_version: Mapped[str] = mapped_column(String(64), default="unknown")


class TestDefinitionRow(Base):
    __tablename__ = "test_definitions"
    __test__ = False

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    steps_csv: Mapped[str] = mapped_column(Text, default="")
    plugin_id: Mapped[str] = mapped_column(String(128), default="default")


class ScenarioRow(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    test_ids_csv: Mapped[str] = mapped_column(Text, default="")
    sut_version: Mapped[str] = mapped_column(String(128), default="unknown")
    history_max_runs: Mapped[int | None] = mapped_column(Integer, nullable=True, default=50)
    history_max_days: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    artifact_max_runs: Mapped[int | None] = mapped_column(Integer, nullable=True, default=20)
    artifact_max_days: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    artifact_keep_failed_only: Mapped[bool] = mapped_column(Boolean, default=True)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), index=True)
    status: Mapped[str] = mapped_column(String(64), default="pending")
    sut_version: Mapped[str] = mapped_column(String(128), default="unknown")
    framework_version: Mapped[str] = mapped_column(String(64), default="unknown")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    events: Mapped[list["EventRow"]] = relationship(back_populates="run")


class EventRow(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    test_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    step_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    error_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifacts_json: Mapped[str] = mapped_column(Text, default="[]")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    contracts_version: Mapped[str] = mapped_column(String(32))

    run: Mapped[RunRow] = relationship(back_populates="events")


class FingerprintOccurrenceRow(Base):
    """Survives run prune so error fingerprints stay visible in history."""

    __tablename__ = "fingerprint_occurrences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scenario_id: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    fingerprint: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(Text, default="")
    test_id: Mapped[str] = mapped_column(String(128), default="")
    step_id: Mapped[str] = mapped_column(String(128), default="")
    sut_version: Mapped[str] = mapped_column(String(128), default="unknown")
    framework_version: Mapped[str] = mapped_column(String(64), default="unknown")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisReportRow(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32))
    scenario_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    test_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def create_engine_from_url(database_url: str):
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """
    Create a session factory.

    - SQLite (unit tests): create tables in-memory via metadata (no Alembic).
    - Postgres (app): expect Alembic migrations (`alembic upgrade head`); do not create_all.
    """
    engine = create_engine_from_url(database_url)
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class SqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_plugin(self, plugin_id: str, framework_version: str) -> None:
        row = self._session.get(PluginRow, plugin_id)
        if row is None:
            self._session.add(PluginRow(id=plugin_id, framework_version=framework_version))
        else:
            row.framework_version = framework_version
        self._session.flush()

    def get_plugin_version(self, plugin_id: str) -> str:
        row = self._session.get(PluginRow, plugin_id)
        return row.framework_version if row else "unknown"

    def replace_plugin_catalog(self, plugin_id: str, tests: list[TestDefinition]) -> None:
        """Set this plugin's catalog to exactly the provided tests (source of truth)."""
        keep_ids = {test.id for test in tests}
        existing = self._session.scalars(
            select(TestDefinitionRow).where(TestDefinitionRow.plugin_id == plugin_id)
        ).all()
        for row in existing:
            if row.id not in keep_ids:
                self._session.delete(row)

        for test in tests:
            row = self._session.get(TestDefinitionRow, test.id)
            steps_csv = ",".join(test.steps)
            if row is None:
                self._session.add(
                    TestDefinitionRow(
                        id=test.id,
                        name=test.name,
                        description=test.description,
                        steps_csv=steps_csv,
                        plugin_id=plugin_id,
                    )
                )
            else:
                row.name = test.name
                row.description = test.description
                row.steps_csv = steps_csv
                row.plugin_id = plugin_id
        self._session.flush()

    def list_tests(self) -> list[TestDefinition]:
        rows = self._session.scalars(select(TestDefinitionRow)).all()
        return [
            TestDefinition(
                id=row.id,
                name=row.name,
                description=row.description,
                steps=[s for s in row.steps_csv.split(",") if s],
            )
            for row in rows
        ]

    def plugin_id_for_test(self, test_id: str) -> str:
        row = self._session.get(TestDefinitionRow, test_id)
        return row.plugin_id if row else "default"

    def create_scenario(
        self,
        scenario_id: str,
        name: str,
        test_ids: list[str],
        *,
        sut_version: str = "unknown",
        history_max_runs: int | None = 50,
        history_max_days: int | None = None,
        artifact_max_runs: int | None = 20,
        artifact_max_days: int | None = None,
        artifact_keep_failed_only: bool = True,
    ) -> None:
        self._session.add(
            ScenarioRow(
                id=scenario_id,
                name=name,
                test_ids_csv=",".join(test_ids),
                sut_version=sut_version,
                history_max_runs=history_max_runs,
                history_max_days=history_max_days,
                artifact_max_runs=artifact_max_runs,
                artifact_max_days=artifact_max_days,
                artifact_keep_failed_only=artifact_keep_failed_only,
            )
        )
        self._session.flush()

    def update_scenario(
        self,
        scenario_id: str,
        *,
        name: str | None = None,
        test_ids: list[str] | None = None,
        sut_version: str | None = None,
        history_max_runs: int | None | object = ...,
        history_max_days: int | None | object = ...,
        artifact_max_runs: int | None | object = ...,
        artifact_max_days: int | None | object = ...,
        artifact_keep_failed_only: bool | object = ...,
    ) -> ScenarioRow | None:
        row = self._session.get(ScenarioRow, scenario_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if test_ids is not None:
            row.test_ids_csv = ",".join(test_ids)
        if sut_version is not None:
            row.sut_version = sut_version
        if history_max_runs is not ...:
            row.history_max_runs = history_max_runs  # type: ignore[assignment]
        if history_max_days is not ...:
            row.history_max_days = history_max_days  # type: ignore[assignment]
        if artifact_max_runs is not ...:
            row.artifact_max_runs = artifact_max_runs  # type: ignore[assignment]
        if artifact_max_days is not ...:
            row.artifact_max_days = artifact_max_days  # type: ignore[assignment]
        if artifact_keep_failed_only is not ...:
            row.artifact_keep_failed_only = bool(artifact_keep_failed_only)
        self._session.flush()
        return row

    def get_scenario(self, scenario_id: str) -> ScenarioRow | None:
        return self._session.get(ScenarioRow, scenario_id)

    def list_scenarios(self) -> list[ScenarioRow]:
        return list(self._session.scalars(select(ScenarioRow)).all())

    def delete_scenario(self, scenario_id: str) -> bool:
        row = self._session.get(ScenarioRow, scenario_id)
        if row is None:
            return False
        runs = self._session.scalars(select(RunRow).where(RunRow.scenario_id == scenario_id)).all()
        for run in runs:
            self._delete_run(run.id)
        self._session.delete(row)
        self._session.flush()
        return True

    def create_run(
        self,
        run_id: str,
        scenario_id: str,
        *,
        sut_version: str,
        framework_version: str,
    ) -> RunRow:
        row = RunRow(
            id=run_id,
            scenario_id=scenario_id,
            status="pending",
            sut_version=sut_version,
            framework_version=framework_version,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_run(self, run_id: str) -> RunRow | None:
        return self._session.get(RunRow, run_id)

    def update_run_status(self, run_id: str, status: str) -> None:
        row = self._session.get(RunRow, run_id)
        if row is not None:
            row.status = status
            self._session.flush()

    def update_run_duration(self, run_id: str, duration_ms: int | None) -> None:
        row = self._session.get(RunRow, run_id)
        if row is not None and duration_ms is not None:
            row.duration_ms = duration_ms
            self._session.flush()

    def append_event(self, event: TestRunEvent) -> None:
        self._session.add(
            EventRow(
                run_id=event.run_id,
                event_type=event.event_type.value,
                test_id=event.test_id,
                step_id=event.step_id,
                status=event.status.value if event.status else None,
                message=event.message,
                error_trace=event.error_trace,
                duration_ms=event.duration_ms,
                artifacts_json=json.dumps([a.model_dump(mode="json") for a in event.artifacts]),
                timestamp=event.timestamp,
                contracts_version=event.contracts_version,
            )
        )
        self._session.flush()
        if event.event_type == TestRunEventType.STEP_FAILED:
            self._record_fingerprint_occurrence(event)

    def _record_fingerprint_occurrence(self, event: TestRunEvent) -> None:
        from test_platform_api.history import error_fingerprint

        run = self.get_run(event.run_id)
        if run is None:
            return
        step_id = event.step_id or "unknown"
        test_id = event.test_id or "unknown"
        digest, label = error_fingerprint(step_id, event.error_trace, event.message)
        self._session.add(
            FingerprintOccurrenceRow(
                scenario_id=run.scenario_id,
                run_id=event.run_id,
                fingerprint=digest,
                label=label,
                test_id=test_id,
                step_id=step_id,
                sut_version=run.sut_version,
                framework_version=run.framework_version,
                message=event.message,
                created_at=event.timestamp,
            )
        )
        self._session.flush()
        self._trim_fingerprint_occurrences(run.scenario_id, keep=100)

    def _trim_fingerprint_occurrences(self, scenario_id: str, *, keep: int) -> None:
        rows = list(
            self._session.scalars(
                select(FingerprintOccurrenceRow)
                .where(FingerprintOccurrenceRow.scenario_id == scenario_id)
                .order_by(FingerprintOccurrenceRow.created_at.desc(), FingerprintOccurrenceRow.id.desc())
            ).all()
        )
        for row in rows[keep:]:
            self._session.delete(row)
        if len(rows) > keep:
            self._session.flush()

    def list_fingerprint_occurrences(self, scenario_id: str) -> list[FingerprintOccurrenceRow]:
        return list(
            self._session.scalars(
                select(FingerprintOccurrenceRow)
                .where(FingerprintOccurrenceRow.scenario_id == scenario_id)
                .order_by(FingerprintOccurrenceRow.created_at.desc(), FingerprintOccurrenceRow.id.desc())
            ).all()
        )

    def list_events(self, run_id: str) -> list[TestRunEvent]:
        rows = self._session.scalars(
            select(EventRow).where(EventRow.run_id == run_id).order_by(EventRow.id)
        ).all()
        return [
            TestRunEvent(
                run_id=row.run_id,
                event_type=TestRunEventType(row.event_type),
                test_id=row.test_id,
                step_id=row.step_id,
                status=StepStatus(row.status) if row.status else None,
                message=row.message,
                error_trace=row.error_trace,
                duration_ms=row.duration_ms,
                artifacts=[ArtifactRef.model_validate(a) for a in json.loads(row.artifacts_json or "[]")],
                timestamp=row.timestamp,
                contracts_version=row.contracts_version,
            )
            for row in rows
        ]

    def list_runs_for_scenario(self, scenario_id: str) -> list[RunRow]:
        return list(
            self._session.scalars(
                select(RunRow)
                .where(RunRow.scenario_id == scenario_id)
                .order_by(RunRow.created_at.desc())
            ).all()
        )

    def prune_scenario_history(
        self,
        scenario_id: str,
        *,
        max_runs: int | None,
        max_days: int | None,
        now: datetime | None = None,
    ) -> int:
        """Keep runs in last max_days ∩ last max_runs. Returns deleted count."""
        now = now or datetime.now(UTC)
        runs = self.list_runs_for_scenario(scenario_id)
        keep: set[str] = {run.id for run in runs}

        if max_days is not None:
            cutoff = now - timedelta(days=max_days)
            keep = set()
            for run in runs:
                created = run.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                if created >= cutoff:
                    keep.add(run.id)

        remaining = [run for run in runs if run.id in keep]
        if max_runs is not None and len(remaining) > max_runs:
            # remaining already newest-first
            keep = {run.id for run in remaining[:max_runs]}

        deleted = 0
        for run in runs:
            if run.id not in keep:
                self._delete_run(run.id)
                deleted += 1
        self._session.flush()
        return deleted

    def _delete_run(self, run_id: str) -> None:
        events = self._session.scalars(select(EventRow).where(EventRow.run_id == run_id)).all()
        for event in events:
            self._session.delete(event)
        run = self._session.get(RunRow, run_id)
        if run is not None:
            self._session.delete(run)

    def save_analysis_report(self, report: AnalysisReport) -> None:
        row = self._session.get(AnalysisReportRow, report.id)
        if row is None:
            self._session.add(
                AnalysisReportRow(
                    id=report.id,
                    scope=report.scope.value,
                    scenario_id=report.scenario_id,
                    run_id=report.run_id,
                    test_id=report.test_id,
                    fingerprint=report.fingerprint,
                    report_json=report.model_dump_json(),
                    created_at=report.generated_at,
                )
            )
        else:
            row.scope = report.scope.value
            row.scenario_id = report.scenario_id
            row.run_id = report.run_id
            row.test_id = report.test_id
            row.fingerprint = report.fingerprint
            row.report_json = report.model_dump_json()
            row.created_at = report.generated_at
        self._session.flush()

    def get_analysis_report(self, analysis_id: str) -> AnalysisReport | None:
        row = self._session.get(AnalysisReportRow, analysis_id)
        if row is None:
            return None
        return AnalysisReport.model_validate_json(row.report_json)

    def find_latest_analysis(
        self,
        *,
        run_id: str,
        scope: str,
        test_id: str | None = None,
    ) -> AnalysisReport | None:
        stmt = (
            select(AnalysisReportRow)
            .where(AnalysisReportRow.run_id == run_id)
            .where(AnalysisReportRow.scope == scope)
            .order_by(AnalysisReportRow.created_at.desc())
        )
        if test_id is not None:
            stmt = stmt.where(AnalysisReportRow.test_id == test_id)
        row = self._session.scalars(stmt).first()
        if row is None:
            return None
        return AnalysisReport.model_validate_json(row.report_json)

    def list_test_analyses_for_run(self, run_id: str) -> list[AnalysisReport]:
        rows = self._session.scalars(
            select(AnalysisReportRow)
            .where(AnalysisReportRow.run_id == run_id)
            .where(AnalysisReportRow.scope == "test")
            .order_by(AnalysisReportRow.created_at.desc())
        ).all()
        # newest per test_id
        by_test: dict[str, AnalysisReport] = {}
        for row in rows:
            report = AnalysisReport.model_validate_json(row.report_json)
            tid = report.test_id or row.test_id
            if tid and tid not in by_test:
                by_test[tid] = report
        return list(by_test.values())
