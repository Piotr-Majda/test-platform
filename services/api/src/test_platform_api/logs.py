from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from test_platform_contracts import (
    StepLogDocument,
    StructuredLogEntry,
    TestLogDocument,
    TestRunEvent,
    TestRunEventType,
)

from test_platform_api.artifact_storage import ArtifactStorage


class LogDocumentError(ValueError):
    pass


def _timestamp(value: Any) -> Any:
    if value:
        return value
    return datetime.now(UTC)


def _entry(payload: dict[str, Any]) -> StructuredLogEntry:
    children = payload.get("children") or []
    return StructuredLogEntry(
        timestamp=_timestamp(payload.get("timestamp") or payload.get("time")),
        layer=str(payload.get("layer") or "framework"),
        component=payload.get("component"),
        level=str(payload.get("level") or "info"),
        message=str(payload.get("message") or "log entry"),
        duration_ms=payload.get("duration_ms"),
        event=payload.get("event"),
        data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
        children=[_entry(child) for child in children if isinstance(child, dict)],
    )


def normalize_step_log(
    payload: dict[str, Any],
    *,
    test_id: str | None = None,
    step_id: str | None = None,
) -> StepLogDocument:
    resolved_step_id = payload.get("step_id") or payload.get("step") or step_id
    if not resolved_step_id:
        raise LogDocumentError("step log is missing step_id")
    entries = payload.get("entries") or []
    return StepLogDocument(
        test_id=payload.get("test_id") or test_id,
        step_id=str(resolved_step_id),
        status=str(payload.get("status") or "unknown"),
        duration_ms=payload.get("duration_ms"),
        entries=[_entry(entry) for entry in entries if isinstance(entry, dict)],
    )


def normalize_test_log(payload: dict[str, Any], *, test_id: str) -> TestLogDocument:
    resolved_test_id = payload.get("test_id") or test_id
    if resolved_test_id != test_id:
        raise LogDocumentError("test log belongs to a different test")
    steps = payload.get("steps") or []
    return TestLogDocument(
        test_id=test_id,
        steps=[
            normalize_step_log(step, test_id=test_id)
            for step in steps
            if isinstance(step, dict)
        ],
    )


def _read_json(storage: ArtifactStorage, key: str) -> dict[str, Any] | None:
    raw = storage.read_bytes(key)
    if raw is None:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LogDocumentError(f"invalid structured log: {key}") from exc
    if not isinstance(payload, dict):
        raise LogDocumentError(f"structured log must be an object: {key}")
    return payload


def _step_artifact_key(
    events: list[TestRunEvent], test_id: str, step_id: str
) -> str | None:
    for event in reversed(events):
        if event.event_type not in {
            TestRunEventType.STEP_FINISHED,
            TestRunEventType.STEP_FAILED,
        }:
            continue
        if event.test_id != test_id or event.step_id != step_id:
            continue
        for artifact in event.artifacts:
            if artifact.name == "step.log.json" or artifact.relative_path.endswith(
                "/step.log.json"
            ):
                return artifact.relative_path
    return None


def load_step_log(
    storage: ArtifactStorage,
    *,
    run_id: str,
    test_id: str,
    step_id: str,
    events: list[TestRunEvent],
) -> StepLogDocument | None:
    event_key = _step_artifact_key(events, test_id, step_id)
    keys = [
        event_key,
        f"{run_id}/{test_id}/{step_id}/step.log.json",
        f"{run_id}/{step_id}/step.log.json",
    ]
    for key in dict.fromkeys(key for key in keys if key):
        payload = _read_json(storage, key)
        if payload is not None:
            return normalize_step_log(payload, test_id=test_id, step_id=step_id)
    return None


def load_test_log(
    storage: ArtifactStorage,
    *,
    run_id: str,
    test_id: str,
    events: list[TestRunEvent],
) -> TestLogDocument | None:
    for key in (f"{run_id}/{test_id}/test.log.json", f"{run_id}/test.log.json"):
        payload = _read_json(storage, key)
        if payload is None:
            continue
        try:
            return normalize_test_log(payload, test_id=test_id)
        except LogDocumentError:
            if key.endswith(f"/{test_id}/test.log.json"):
                raise

    steps: list[StepLogDocument] = []
    seen: set[str] = set()
    for event in events:
        if event.test_id != test_id or not event.step_id or event.step_id in seen:
            continue
        if event.event_type not in {
            TestRunEventType.STEP_FINISHED,
            TestRunEventType.STEP_FAILED,
        }:
            continue
        document = load_step_log(
            storage,
            run_id=run_id,
            test_id=test_id,
            step_id=event.step_id,
            events=events,
        )
        if document is not None:
            steps.append(document)
            seen.add(event.step_id)
    return TestLogDocument(test_id=test_id, steps=steps) if steps else None
