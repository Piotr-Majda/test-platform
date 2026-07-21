import json
import uuid
from pathlib import Path
from typing import Any, Protocol

from test_platform_contracts import ArtifactKind, ArtifactRef

from test_platform_executor.framework.context import StepContext


class ArtifactStore(Protocol):
    def write_text(self, relative_path: str, content: str, content_type: str) -> ArtifactRef: ...


class LocalArtifactStore:
    def __init__(self, root: Path, run_id: str) -> None:
        self._root = root
        self._run_id = run_id
        self._run_dir = root / run_id
        self._run_dir.mkdir(parents=True, exist_ok=True)

    def write_text(self, relative_path: str, content: str, content_type: str) -> ArtifactRef:
        path = self._run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        kind = ArtifactKind.OTHER
        if content_type == "text/html":
            kind = ArtifactKind.HTML_SNAPSHOT
        elif content_type.startswith("application/json") or relative_path.endswith(".json"):
            kind = ArtifactKind.LOG
        elif relative_path.endswith(".log") or content_type == "text/plain":
            kind = ArtifactKind.LOG
        return ArtifactRef(
            id=str(uuid.uuid4()),
            kind=kind,
            name=path.name,
            content_type=content_type,
            relative_path=f"{self._run_id}/{relative_path}".replace("\\", "/"),
        )


class ArtifactStrategy(Protocol):
    def collect(
        self,
        context: StepContext,
        step_id: str,
        *,
        failed: bool,
        step_log: dict[str, Any],
    ) -> list[ArtifactRef]: ...


class NoArtifactStrategy:
    def collect(
        self,
        context: StepContext,
        step_id: str,
        *,
        failed: bool,
        step_log: dict[str, Any],
    ) -> list[ArtifactRef]:
        return []


class HtmlSnapshotArtifactStrategy:
    """Always attach step + test JSON logs (pass and fail); HTML snapshot only on failure."""

    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def collect(
        self,
        context: StepContext,
        step_id: str,
        *,
        failed: bool,
        step_log: dict[str, Any],
    ) -> list[ArtifactRef]:
        artifacts: list[ArtifactRef] = []
        # Pass and fail — needed to audit false positives / positive execution trail
        artifacts.append(
            self._store.write_text(
                f"{step_id}/step.log.json",
                json.dumps(step_log, separators=(",", ":")),
                "application/json",
            )
        )
        # Per-test aggregated log (avoids multi-test scenarios overwriting each other)
        test_id = context.log.test_id
        test_log_path = f"{test_id}/test.log.json" if test_id else "test.log.json"
        artifacts.append(
            self._store.write_text(
                test_log_path,
                json.dumps(context.log.test_document(), separators=(",", ":")),
                "application/json",
            )
        )
        # Large HTML snapshots only when analyzing a failure (main prior perf hit)
        if failed:
            html = context.data.get("page_html")
            if isinstance(html, str) and html:
                artifacts.append(
                    self._store.write_text(f"{step_id}/page.html", html, "text/html")
                )
        return artifacts
