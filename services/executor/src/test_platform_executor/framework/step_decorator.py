import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

from test_platform_contracts import StepStatus, TestRunEvent, TestRunEventType

from test_platform_executor.framework.artifacts import ArtifactStrategy, NoArtifactStrategy
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import (
    get_emitter,
    get_run_id,
    get_test_id,
    record_action_ms,
)
from test_platform_executor.framework.steps import StepFailedError

T = TypeVar("T")


def step(name: str) -> Callable[[type[T]], type[T]]:
    """Class decorator: names the step and emits status/duration/artifacts via contextvar emitter."""

    def decorator(cls: type[T]) -> type[T]:
        original_execute = cls.execute  # type: ignore[attr-defined]

        def execute(self, context: StepContext) -> None:  # type: ignore[no-untyped-def]
            strategy: ArtifactStrategy = getattr(self, "artifact_strategy", NoArtifactStrategy())
            context.log.begin_step(name)
            context.reset_action_timer()
            failed = False
            error_trace: str | None = None
            message = f"step finished: {name}"
            try:
                original_execute(self, context)
            except StepFailedError as exc:
                failed = True
                message = str(exc)
                error_trace = traceback.format_exc()
                raise
            except Exception as exc:
                failed = True
                message = str(exc)
                error_trace = traceback.format_exc()
                raise
            finally:
                # SUT action time only — excludes log finalize, artifact I/O, and emit
                duration_ms = context.consume_action_ms()
                record_action_ms(duration_ms)
                step_log = context.log.finish_step(failed=failed)
                artifacts = strategy.collect(
                    context,
                    name,
                    failed=failed,
                    step_log=step_log,
                )
                _emit_step(
                    name=name,
                    failed=failed,
                    message=message,
                    error_trace=error_trace,
                    duration_ms=duration_ms,
                    artifacts=artifacts,
                )

        cls.id = name  # type: ignore[attr-defined]
        cls.execute = execute  # type: ignore[attr-defined]
        return cls

    return decorator


def _emit_step(
    *,
    name: str,
    failed: bool,
    message: str,
    error_trace: str | None,
    duration_ms: int,
    artifacts: list,
) -> None:
    get_emitter()(
        TestRunEvent(
            run_id=get_run_id(),
            event_type=TestRunEventType.STEP_FAILED if failed else TestRunEventType.STEP_FINISHED,
            test_id=get_test_id(),
            step_id=name,
            status=StepStatus.FAILED if failed else StepStatus.SUCCESS,
            message=message,
            error_trace=error_trace,
            duration_ms=duration_ms,
            artifacts=artifacts,
            timestamp=datetime.now(UTC),
        )
    )
