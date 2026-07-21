from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from test_platform_api.paths import artifacts_dir


class ArtifactStorage(Protocol):
    def read_bytes(self, key: str) -> bytes | None: ...
    def size(self, key: str) -> int | None: ...
    def list_keys(self, prefix: str) -> list[str]: ...
    def delete_prefix(self, prefix: str) -> int: ...


def _safe_key(key: str) -> str:
    normalized = str(PurePosixPath(key.replace("\\", "/")))
    if not normalized or normalized == "." or normalized.startswith("/"):
        raise ValueError("invalid artifact key")
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError("invalid artifact key")
    return normalized


class LocalArtifactStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / _safe_key(key)).resolve()
        path.relative_to(self._root)
        return path

    def read_bytes(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def size(self, key: str) -> int | None:
        path = self._path(key)
        return path.stat().st_size if path.is_file() else None

    def list_keys(self, prefix: str) -> list[str]:
        path = self._path(prefix)
        if not path.is_dir():
            return []
        return [
            item.relative_to(self._root).as_posix()
            for item in path.rglob("*")
            if item.is_file()
        ]

    def delete_prefix(self, prefix: str) -> int:
        import shutil

        path = self._path(prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            return 1
        if path.is_file():
            path.unlink(missing_ok=True)
            return 1
        return 0


class S3ArtifactStorage:
    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    def read_bytes(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=_safe_key(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return response["Body"].read()

    def size(self, key: str) -> int | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=_safe_key(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return int(response["ContentLength"])

    def list_keys(self, prefix: str) -> list[str]:
        safe_prefix = _safe_key(prefix).rstrip("/") + "/"
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=safe_prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return keys

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_keys(prefix)
        for start in range(0, len(keys), 1000):
            batch = keys[start : start + 1000]
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )
        return 1 if keys else 0


def artifact_storage() -> ArtifactStorage:
    bucket = os.getenv("S3_BUCKET") or os.getenv("AWS_S3_BUCKET_NAME", "")
    if not bucket:
        return _storage_for_config(("local", str(artifacts_dir())))
    config = (
        "s3",
        bucket,
        os.getenv("S3_ENDPOINT_URL") or os.environ["AWS_ENDPOINT_URL"],
        os.getenv("S3_ACCESS_KEY_ID") or os.environ["AWS_ACCESS_KEY_ID"],
        os.getenv("S3_SECRET_ACCESS_KEY") or os.environ["AWS_SECRET_ACCESS_KEY"],
        os.getenv("S3_REGION") or os.getenv("AWS_DEFAULT_REGION", "auto"),
    )
    return _storage_for_config(config)


@lru_cache(maxsize=16)
def _storage_for_config(config: tuple[str, ...]) -> ArtifactStorage:
    if config[0] == "local":
        return LocalArtifactStorage(Path(config[1]))
    _, bucket, endpoint, access_key, secret_key, region = config
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(s3={"addressing_style": "virtual"}),
    )
    return S3ArtifactStorage(bucket, client)
