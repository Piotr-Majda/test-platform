import redis
from test_platform_contracts import (
    EVENTS_STREAM,
    EXECUTE_STREAM,
    ExecuteTestCommand,
    TestRunEvent,
    decode_stream_payload,
    encode_stream_payload,
)


class RedisEventPublisher:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def publish_execute(self, command: ExecuteTestCommand) -> None:
        self._client.xadd(EXECUTE_STREAM, encode_stream_payload(command))


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.commands: list[ExecuteTestCommand] = []

    def publish_execute(self, command: ExecuteTestCommand) -> None:
        self.commands.append(command)


class RedisEventConsumer:
    """Reads progress events from Redis Streams into the API store."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def read_new(self, last_id: str = "0-0", count: int = 100) -> tuple[str, list[TestRunEvent]]:
        entries = self._client.xread({EVENTS_STREAM: last_id}, count=count, block=None)
        if not entries:
            return last_id, []

        events: list[TestRunEvent] = []
        newest = last_id
        for _stream, messages in entries:
            for message_id, fields in messages:
                newest = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
                decoded_fields = {
                    (k.decode() if isinstance(k, bytes) else k): (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in fields.items()
                }
                try:
                    events.append(decode_stream_payload(decoded_fields, TestRunEvent))
                except Exception:
                    # Skip legacy / unknown payloads so the poller can advance
                    continue
        return newest, events
