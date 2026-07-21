from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterator


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class LogNode:
    layer: str
    message: str
    time: str
    component: str | None = None
    event: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    children: list[LogNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "layer": self.layer,
            "time": self.time,
            "message": self.message,
        }
        if self.component is not None:
            payload["component"] = self.component
        if self.event is not None:
            payload["event"] = self.event
        if self.data:
            payload["data"] = self.data
        if self.children:
            payload["children"] = [child.to_dict() for child in self.children]
        return payload


class ScopedLogger:
    """Stack of scopes: domain push → adapter push → framework log → pop."""

    def __init__(self, test_id: str | None = None) -> None:
        self.test_id = test_id
        self._stack: list[LogNode] = []
        self._current_roots: list[LogNode] = []
        self._current_step: str | None = None
        self._steps: dict[str, dict[str, Any]] = {}

    def begin_step(self, step_id: str) -> None:
        self._current_step = step_id
        self._stack = []
        self._current_roots = []

    def finish_step(self, *, failed: bool) -> dict[str, Any]:
        if self._current_step is None:
            raise RuntimeError("finish_step called without begin_step")
        if self._stack:
            raise RuntimeError("unbalanced log scopes — stack not empty at step end")
        document = {
            "step": self._current_step,
            "status": "failed" if failed else "success",
            "entries": [node.to_dict() for node in self._current_roots],
        }
        self._steps[self._current_step] = document
        self._current_step = None
        self._current_roots = []
        return document

    def test_document(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "steps": list(self._steps.values()),
        }

    def log(
        self,
        layer: str,
        message: str,
        *,
        component: str | None = None,
        event: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> LogNode:
        node = LogNode(
            layer=layer,
            message=message,
            time=_now(),
            component=component,
            event=event,
            data=data or {},
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
        event: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Iterator[LogNode]:
        node = self.log(
            layer,
            message,
            component=component,
            event=event,
            data=data,
        )
        self._stack.append(node)
        try:
            yield node
        finally:
            self._stack.pop()
