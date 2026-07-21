from typing import Protocol

from test_platform_executor.framework.context import StepContext


class Step(Protocol):
    id: str

    def execute(self, context: StepContext) -> None: ...


class StepFailedError(Exception):
    def __init__(self, step_id: str, message: str) -> None:
        self.step_id = step_id
        super().__init__(message)
