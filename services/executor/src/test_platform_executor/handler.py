from test_platform_contracts import ExecuteTestCommand

from test_platform_executor.events import ProgressPublisher
from test_platform_executor.pytest_runner import run_with_pytest


def process_execute_command(
    command: ExecuteTestCommand,
    publisher: ProgressPublisher,
) -> bool:
    exit_code = run_with_pytest(command, publisher)
    return exit_code == 0
