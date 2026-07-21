from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Iterator

from test_platform_contracts import StepLogDocument, StructuredLogEntry, TestLogDocument


class ScopedLogger:
    """Stack of scopes: domain push → adapter push → framework log → pop."""

    def __init__(self, test_id: str | None = None) -> None:
        self.test_id = test_id
        self._stack: list[StructuredLogEntry] = []
        self._current_roots: list[StructuredLogEntry] = []
        self._current_step: str | None = None
        self._steps: list[StepLogDocument] = []

    def begin_step(self, step_id: str) -> None:
        self._current_step = step_id
        self._stack = []
        self._current_roots = []

    def finish_step(self, *, failed: bool, duration_ms: int | None = None) -> dict[str, Any]:
        if self._current_step is None:
            raise RuntimeError("finish_step called without begin_step")
        if self._stack:
            raise RuntimeError("unbalanced log scopes — stack not empty at step end")
        document = StepLogDocument(
            test_id=self.test_id,
            step_id=self._current_step,
            status="failed" if failed else "success",
            duration_ms=duration_ms,
            entries=self._current_roots,
        )
        self._steps.append(document)
        self._current_step = None
        self._current_roots = []
        return document.model_dump(mode="json", exclude_none=True)

    def test_document(self) -> dict[str, Any]:
        if not self.test_id:
            raise RuntimeError("test_document requires a test_id")
        return TestLogDocument(test_id=self.test_id, steps=self._steps).model_dump(
            mode="json", exclude_none=True
        )

    def log(
        self,
        layer: str,
        message: str,
        *,
        component: str | None = None,
        level: str = "info",
        event: str | None = None,
        data: dict[str, Any] | None = None,
        duration_ms: int | None = None,
    ) -> StructuredLogEntry:
        node = StructuredLogEntry(
            layer=layer,
            message=message,
            timestamp=datetime.now(UTC),
            component=component,
            level=level,
            event=event,
            data=data or {},
            duration_ms=duration_ms,
        )
        if self._stack:
            self._stack[-1].children.append(node)
        else:
            self._current_roots.append(node)
        return node

    @contextmanager
    def scope(
        self,
        layer: str,
        message: str,
        *,
        component: str | None = None,
        level: str = "info",
        event: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Iterator[StructuredLogEntry]:
        node = self.log(
            layer,
            message,
            component=component,
            level=level,
            event=event,
            data=data,
        )
        started = perf_counter()
        self._stack.append(node)
        try:
            yield node
        finally:
            self._stack.pop()
            node.duration_ms = max(0, round((perf_counter() - started) * 1000))
