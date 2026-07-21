"""Duration helper — Given / When / Then."""

import time

from test_platform_executor.framework import timing


def test_sub_millisecond_elapsed_reports_at_least_one_ms(monkeypatch) -> None:
    # Given: 0.2 ms elapsed between start and now
    monkeypatch.setattr(timing.time, "perf_counter", lambda: 100.0 + 0.0002)

    # When
    result = timing.duration_ms_since(100.0)

    # Then
    assert result == 1


def test_multi_millisecond_elapsed_is_ceiled() -> None:
    started = time.perf_counter()
    time.sleep(0.003)

    assert timing.duration_ms_since(started) >= 3
