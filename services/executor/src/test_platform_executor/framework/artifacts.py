import json
import os
import uuid
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config

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


class S3ArtifactStore:
    """Artifact writer for S3-compatible stores, including Railway Buckets."""

    def __init__(self, bucket: str, run_id: str, client: Any) -> None:
        self._bucket = bucket
        self._run_id = run_id
        self._client = client

    def write_text(self, relative_path: str, content: str, content_type: str) -> ArtifactRef:
        key = f"{self._run_id}/{relative_path}".replace("\\", "/")
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType=content_type,
        )
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
            name=Path(relative_path).name,
            content_type=content_type,
            relative_path=key,
        )


def create_artifact_store(root: Path, run_id: str) -> ArtifactStore:
    """Use S3 when configured; retain local storage for development and tests."""
    bucket = os.getenv("S3_BUCKET") or os.getenv("AWS_S3_BUCKET_NAME")
    if not bucket:
        return LocalArtifactStore(root, run_id)
    endpoint = os.getenv("S3_ENDPOINT_URL") or os.environ["AWS_ENDPOINT_URL"]
    access_key = os.getenv("S3_ACCESS_KEY_ID") or os.environ["AWS_ACCESS_KEY_ID"]
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY") or os.environ["AWS_SECRET_ACCESS_KEY"]
    region = os.getenv("S3_REGION") or os.getenv("AWS_DEFAULT_REGION", "auto")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(s3={"addressing_style": "virtual"}),
    )
    return S3ArtifactStore(bucket, run_id, client)


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
