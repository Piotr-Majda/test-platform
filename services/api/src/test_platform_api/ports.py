from typing import Protocol

from test_platform_contracts import ExecuteTestCommand, TestRunEvent


class EventPublisher(Protocol):
    def publish_execute(self, command: ExecuteTestCommand) -> None: ...


class EventStore(Protocol):
    def append(self, event: TestRunEvent) -> None: ...

    def list_for_run(self, run_id: str) -> list[TestRunEvent]: ...
