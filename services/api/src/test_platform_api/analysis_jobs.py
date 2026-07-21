"""Background analysis jobs so the HTTP request returns quickly."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import uuid

from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker
from test_platform_contracts import AnalysisReport, AnalysisRequest

from test_platform_api.analysis import FailureAnalyzer, run_analysis
from test_platform_api.db import SqlAlchemyRepository


class AnalysisJobStatus(BaseModel):
    id: str = Field(min_length=1)
    status: str  # pending | completed | failed
    report: AnalysisReport | None = None
    error: str | None = None


@dataclass
class _Job:
    status: str
    report: AnalysisReport | None = None
    error: str | None = None


class AnalysisJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._lock = Lock()

    def create_pending(self) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = _Job(status="pending")
        return job_id

    def complete(self, job_id: str, report: AnalysisReport) -> None:
        with self._lock:
            self._jobs[job_id] = _Job(status="completed", report=report)

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            self._jobs[job_id] = _Job(status="failed", error=error)

    def get(self, job_id: str) -> AnalysisJobStatus | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return AnalysisJobStatus(
                id=job_id,
                status=job.status,
                report=job.report,
                error=job.error,
            )


def start_analysis_job(
    *,
    store: AnalysisJobStore,
    session_factory: sessionmaker,
    analyzer: FailureAnalyzer,
    request: AnalysisRequest,
) -> AnalysisJobStatus:
    job_id = store.create_pending()

    def work() -> None:
        session = session_factory()
        try:
            repo = SqlAlchemyRepository(session)
            report = run_analysis(repo, request, analyzer)
            session.commit()
            store.complete(job_id, report)
        except Exception as exc:  # noqa: BLE001 — surface to job status for UI
            session.rollback()
            store.fail(job_id, str(exc))
        finally:
            session.close()

    import threading

    threading.Thread(target=work, name=f"analysis-{job_id[:8]}", daemon=True).start()
    return AnalysisJobStatus(id=job_id, status="pending")
