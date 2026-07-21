import math
import time


def duration_ms_since(started: float) -> int:
    """Wall time in whole milliseconds.

    Sub-millisecond work rounds up to 1 ms so UI never shows misleading 0
    for a step that actually ran.
    """
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms <= 0:
        return 0
    return max(1, math.ceil(elapsed_ms))
