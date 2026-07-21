from typing import Protocol

import redis
from test_platform_contracts import EVENTS_STREAM, TestRunEvent, encode_stream_payload


class ProgressPublisher(Protocol):
    def publish(self, event: TestRunEvent) -> None: ...


class RedisProgressPublisher:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def publish(self, event: TestRunEvent) -> None:
        self._client.xadd(EVENTS_STREAM, encode_stream_payload(event))


class InMemoryProgressPublisher:
    def __init__(self) -> None:
        self.events: list[TestRunEvent] = []

    def publish(self, event: TestRunEvent) -> None:
        self.events.append(event)
