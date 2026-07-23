from test_platform_contracts import TestDefinition


def catalog_definitions() -> list[TestDefinition]:
    """Static catalog advertised to the platform API (pytest discovers the real suite)."""
    return [
        TestDefinition(
            id="google_title",
            name="Google page title",
            description="Open Google and assert the page title contains Google",
            steps=["open_page", "assert_title"],
        ),
        TestDefinition(
            id="flaky_coin",
            name="Flaky coin flip",
            description="Demo test that fails ~40% of the time for history / flakiness UI",
            steps=["coin_flip"],
        ),
        TestDefinition(
            id="justjoin_python_roles",
            name="JustJoinIT Python roles",
            description=(
                "Fetch live JustJoinIT python offers, keep 10 Python-related titles+urls, "
                "GET-check the first 3 offer pages return 200"
            ),
            steps=["fetch_python_offers", "extract_python_roles", "assert_offer_urls"],
        ),
        TestDefinition(
            id="youtube_ai_engineer_latest",
            name="YouTube AI Engineer latest",
            description=(
                "Fetch AI Engineer channel RSS, take newest video, validate its metadata, "
                "write extractive summary from description"
            ),
            steps=[
                "fetch_channel_feed",
                "extract_latest_video",
                "assert_latest_video_metadata",
                "summarize_latest_video",
            ],
        ),
    ]
