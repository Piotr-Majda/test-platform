"""YouTube AI Engineer latest video summary — Given / When / Then."""

import pytest
from test_platform_contracts import TestRunEventType

from test_platform_executor.events import InMemoryProgressPublisher
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import set_emission_context
from test_platform_executor.framework.steps import StepFailedError
from test_platform_executor.framework.youtube_client import (
    FakeYoutubeChannelClient,
    YoutubeVideo,
    extractive_summary,
    parse_latest_video,
)
from test_platform_executor.framework.youtube_steps import (
    AssertLatestVideoMetadataStep,
    ExtractLatestVideoStep,
    FetchChannelFeedStep,
    SummarizeLatestVideoStep,
)

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
 <title>AI Engineer</title>
 <entry>
  <id>yt:video:abc123XYZ</id>
  <yt:videoId>abc123XYZ</yt:videoId>
  <title>Building Agents with Tools</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=abc123XYZ"/>
  <published>2026-07-18T12:00:00+00:00</published>
  <media:group>
   <media:description>A deep dive into tool-calling agents for production systems. We cover planning, memory, and evaluation.</media:description>
  </media:group>
 </entry>
 <entry>
  <id>yt:video:older99</id>
  <yt:videoId>older99</yt:videoId>
  <title>Older talk</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=older99"/>
  <published>2026-01-01T12:00:00+00:00</published>
 </entry>
</feed>
"""


@pytest.fixture(autouse=True)
def emission() -> InMemoryProgressPublisher:
    publisher = InMemoryProgressPublisher()
    set_emission_context(
        emitter=publisher.publish,
        run_id="run-yt",
        test_id="youtube_ai_engineer_latest",
    )
    return publisher


def test_parse_latest_video_takes_first_feed_entry() -> None:
    video = parse_latest_video(SAMPLE_FEED)

    assert video.video_id == "abc123XYZ"
    assert video.title == "Building Agents with Tools"
    assert video.url == "https://www.youtube.com/watch?v=abc123XYZ"
    assert "tool-calling" in video.description


def test_extractive_summary_prefers_description() -> None:
    summary = extractive_summary(
        "A deep dive into tool-calling agents for production systems.",
        "Building Agents with Tools",
        max_chars=80,
    )
    assert "tool-calling" in summary
    assert summary.endswith("…") or len(summary) <= 80


def test_happy_path_fetch_extract_assert_summarize(emission: InMemoryProgressPublisher) -> None:
    client = FakeYoutubeChannelClient(feed_xml=SAMPLE_FEED)
    context = StepContext()

    FetchChannelFeedStep(client).execute(context)
    ExtractLatestVideoStep().execute(context)
    AssertLatestVideoMetadataStep().execute(context)
    SummarizeLatestVideoStep().execute(context)

    assert "tool-calling" in context.get("youtube_summary")
    steps = {e.step_id for e in emission.events if e.event_type == TestRunEventType.STEP_FINISHED}
    assert steps == {
        "fetch_channel_feed",
        "extract_latest_video",
        "assert_latest_video_metadata",
        "summarize_latest_video",
    }


def test_assert_fails_when_watch_url_does_not_match_video_id() -> None:
    context = StepContext()
    context.set(
        "youtube_latest_video",
        YoutubeVideo(
            video_id="abc123XYZ",
            title="Building Agents with Tools",
            url="https://www.youtube.com/watch?v=differentVideo",
            published="2026-07-18T12:00:00+00:00",
            description="Description",
        ),
    )

    with pytest.raises(StepFailedError, match="invalid YouTube watch URL"):
        AssertLatestVideoMetadataStep().execute(context)
