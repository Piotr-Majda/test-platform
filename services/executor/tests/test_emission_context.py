"""Emission context must not wipe test_id set by pytest_runtest_setup."""

from test_platform_executor.framework.emission import (
    clear_emission_context,
    get_test_id,
    set_emission_context,
    set_test_id,
)


def test_set_emission_context_preserves_existing_test_id() -> None:
    try:
        set_test_id("google_title")
        set_emission_context(emitter=lambda _e: None, run_id="r1")
        assert get_test_id() == "google_title"
    finally:
        clear_emission_context()


def test_set_emission_context_can_override_test_id() -> None:
    try:
        set_test_id("google_title")
        set_emission_context(emitter=lambda _e: None, run_id="r1", test_id="youtube_ai_engineer_latest")
        assert get_test_id() == "youtube_ai_engineer_latest"
    finally:
        clear_emission_context()
