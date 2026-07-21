from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import time
from typing import Any

from test_platform_executor.framework.scoped_log import ScopedLogger
from test_platform_executor.framework.timing import duration_ms_since


@dataclass
class StepContext:
    """Shared mutable state passed between steps in a scenario."""

    data: dict[str, Any] = field(default_factory=dict)
    log: ScopedLogger = field(default_factory=ScopedLogger)
    _action_ms: int = 0

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str) -> Any:
        return self.data[key]

    def reset_action_timer(self) -> None:
        self._action_ms = 0

    def consume_action_ms(self) -> int:
        value = self._action_ms
        self._action_ms = 0
        return value

    @contextmanager
    def timed_action(self) -> Iterator[None]:
        """Measure only SUT-facing work (excludes logging / emit / artifacts)."""
        started = time.perf_counter()
        try:
            yield
        finally:
            self._action_ms += duration_ms_since(started)
