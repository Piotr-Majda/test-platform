from typing import TypeVar

from pydantic import BaseModel

EXECUTE_STREAM = "test-platform:execute"
EVENTS_STREAM = "test-platform:events"
EXECUTE_GROUP = "test-platform-workers"

T = TypeVar("T", bound=BaseModel)


def encode_stream_payload(model: BaseModel) -> dict[str, str]:
    return {"payload": model.model_dump_json()}


def decode_stream_payload(fields: dict[str, str], model_type: type[T]) -> T:
    raw = fields.get("payload")
    if raw is None:
        raise ValueError("stream fields missing 'payload'")
    return model_type.model_validate_json(raw)
