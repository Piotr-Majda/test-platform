from collections.abc import Callable
from contextvars import ContextVar

from test_platform_contracts import TestRunEvent

EventEmitter = Callable[[TestRunEvent], None]

_emitter: ContextVar[EventEmitter | None] = ContextVar("test_platform_emitter", default=None)
_run_id: ContextVar[str | None] = ContextVar("test_platform_run_id", default=None)
_test_id: ContextVar[str | None] = ContextVar("test_platform_test_id", default=None)
_action_ms: ContextVar[int] = ContextVar("test_platform_action_ms", default=0)
# Module fallback — nested pytest.main can lose ContextVar in edge cases
_active_test_id: str | None = None


def set_emission_context(
    *,
    emitter: EventEmitter,
    run_id: str,
    test_id: str | None = None,
) -> None:
    """
    Bind emitter/run for the current pytest fixture scope.

    When test_id is omitted, keep any id already set by pytest_runtest_setup —
    the platform_emitter fixture must not wipe it (that caused null step.test_id).
    """
    global _active_test_id
    _emitter.set(emitter)
    _run_id.set(run_id)
    if test_id is not None:
        _test_id.set(test_id)
        _active_test_id = test_id
    _action_ms.set(0)


def clear_emission_context() -> None:
    global _active_test_id
    _emitter.set(None)
    _run_id.set(None)
    _test_id.set(None)
    _active_test_id = None
    _action_ms.set(0)


def get_emitter() -> EventEmitter:
    emitter = _emitter.get()
    if emitter is None:
        raise RuntimeError("emitter not set — use pytest fixture / set_emission_context")
    return emitter


def get_run_id() -> str:
    run_id = _run_id.get()
    if run_id is None:
        raise RuntimeError("run_id not set in emission context")
    return run_id


def get_test_id() -> str | None:
    return _test_id.get() or _active_test_id


def set_test_id(test_id: str) -> None:
    global _active_test_id
    _test_id.set(test_id)
    _active_test_id = test_id
    _action_ms.set(0)


def record_action_ms(ms: int) -> None:
    """Accumulate SUT action time for the current test."""
    _action_ms.set(_action_ms.get() + max(0, ms))


def take_test_action_ms() -> int:
    """Return and clear accumulated SUT action time for the current test."""
    value = _action_ms.get()
    _action_ms.set(0)
    return value
