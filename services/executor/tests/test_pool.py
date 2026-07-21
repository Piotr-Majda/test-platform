"""Worker pool consumes execute commands — Given / When / Then."""

import time

import fakeredis
from test_platform_contracts import (
    CONTRACTS_VERSION,
    EXECUTE_STREAM,
    ExecuteTestCommand,
    encode_stream_payload,
)

from test_platform_executor.pool import WorkerPool


def test_pool_invokes_handler_for_execute_message() -> None:
    # Given
    client = fakeredis.FakeRedis(decode_responses=True)
    seen: list[ExecuteTestCommand] = []

    def handler(command: ExecuteTestCommand) -> None:
        seen.append(command)

    pool = WorkerPool(client, handler, worker_count=1, consumer_prefix="test")
    pool.start()
    command = ExecuteTestCommand(
        run_id="run-pool",
        scenario_id="scenario-1",
        test_ids=["google_title"],
        contracts_version=CONTRACTS_VERSION,
    )

    # When
    client.xadd(EXECUTE_STREAM, encode_stream_payload(command))
    deadline = time.time() + 3
    while not seen and time.time() < deadline:
        time.sleep(0.05)
    pool.stop()

    # Then
    assert len(seen) == 1
    assert seen[0].run_id == "run-pool"


def test_pool_rejects_zero_workers() -> None:
    # Given
    client = fakeredis.FakeRedis(decode_responses=True)

    # When / Then
    try:
        WorkerPool(client, lambda _c: None, worker_count=0)
        raised = False
    except ValueError:
        raised = True
    assert raised is True
