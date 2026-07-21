"""Redis stream payload helpers — Given / When / Then."""

from test_platform_contracts import (
    CONTRACTS_VERSION,
    EXECUTE_STREAM,
    EVENTS_STREAM,
    ExecuteTestCommand,
    decode_stream_payload,
    encode_stream_payload,
)


def test_encode_decode_execute_command() -> None:
    # Given
    command = ExecuteTestCommand(
        run_id="run-1",
        scenario_id="scenario-1",
        test_ids=["google_title"],
        contracts_version=CONTRACTS_VERSION,
    )

    # When
    fields = encode_stream_payload(command)
    restored = decode_stream_payload(fields, ExecuteTestCommand)

    # Then
    assert restored == command
    assert "payload" in fields


def test_stream_names_are_stable() -> None:
    # Given / When / Then
    assert EXECUTE_STREAM == "test-platform:execute"
    assert EVENTS_STREAM == "test-platform:events"
