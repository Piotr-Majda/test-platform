import os
from pathlib import Path

import pytest

from test_platform_contracts import ExecuteTestCommand
from test_platform_executor import pytest_plugin
from test_platform_executor.events import ProgressPublisher
from test_platform_executor.paths import artifacts_dir


def run_with_pytest(command: ExecuteTestCommand, publisher: ProgressPublisher) -> int:
    suite_dir = Path(__file__).resolve().parent / "suite"
    pytest_plugin.configure_platform_run(publisher, command.run_id, list(command.test_ids))
    os.environ["ARTIFACTS_DIR"] = str(artifacts_dir())
    args = [
        str(suite_dir),
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "test_platform_executor.pytest_plugin",
        f"--platform-run-id={command.run_id}",
        f"--platform-test-ids={','.join(command.test_ids)}",
    ]
    return pytest.main(args)
