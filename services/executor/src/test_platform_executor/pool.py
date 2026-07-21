import logging
import threading
import time
from collections.abc import Callable

import redis
from test_platform_contracts import (
    EXECUTE_GROUP,
    EXECUTE_STREAM,
    ExecuteTestCommand,
    decode_stream_payload,
)

logger = logging.getLogger(__name__)

CommandHandler = Callable[[ExecuteTestCommand], None]



class WorkerPool:
    """N long-lived workers consuming execute commands from a Redis consumer group."""

    def __init__(
        self,
        client: redis.Redis,
        handler: CommandHandler,
        worker_count: int = 2,
        consumer_prefix: str = "worker",
    ) -> None:
        if worker_count < 1:
            raise ValueError("worker_count must be >= 1")
        self._client = client
        self._handler = handler
        self._worker_count = worker_count
        self._consumer_prefix = consumer_prefix
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def ensure_group(self) -> None:
        try:
            self._client.xgroup_create(EXECUTE_STREAM, EXECUTE_GROUP, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def start(self) -> None:
        self.ensure_group()
        self._stop.clear()
        for index in range(self._worker_count):
            name = f"{self._consumer_prefix}-{index}"
            thread = threading.Thread(target=self._loop, args=(name,), name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads.clear()

    def _loop(self, consumer_name: str) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once(consumer_name)
            except Exception:
                logger.exception("worker %s failed while polling", consumer_name)
                time.sleep(0.5)

    def _poll_once(self, consumer_name: str) -> None:
        entries = self._client.xreadgroup(
            groupname=EXECUTE_GROUP,
            consumername=consumer_name,
            streams={EXECUTE_STREAM: ">"},
            count=1,
            block=1000,
        )
        if not entries:
            return

        for _stream, messages in entries:
            for message_id, fields in messages:
                msg_id = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
                decoded = {
                    (k.decode() if isinstance(k, bytes) else k): (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in fields.items()
                }
                command = decode_stream_payload(decoded, ExecuteTestCommand)
                try:
                    self._handler(command)
                finally:
                    self._client.xack(EXECUTE_STREAM, EXECUTE_GROUP, msg_id)
