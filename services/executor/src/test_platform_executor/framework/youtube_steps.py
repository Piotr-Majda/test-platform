from __future__ import annotations

from test_platform_executor.framework.artifacts import ArtifactStrategy, NoArtifactStrategy
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.step_decorator import step
from test_platform_executor.framework.steps import StepFailedError
from test_platform_executor.framework.youtube_client import (
    YoutubeChannelClient,
    YoutubeVideo,
    extractive_summary,
    parse_latest_video,
)


@step("fetch_channel_feed")
class FetchChannelFeedStep:
    def __init__(
        self,
        client: YoutubeChannelClient,
        artifact_strategy: ArtifactStrategy | None = None,
    ) -> None:
        self._client = client
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            "Fetch AI Engineer YouTube channel feed",
            component="fetch_channel_feed",
            event="feed.fetch",
        ):
            xml = self._client.fetch_feed_xml(context)
            context.set("youtube_feed_xml", xml)
            context.log.log(
                "domain",
                f"Feed loaded ({len(xml)} chars)",
                component="fetch_channel_feed",
                event="feed.loaded",
                data={"bytes": len(xml)},
            )


@step("extract_latest_video")
class ExtractLatestVideoStep:
    def __init__(self, artifact_strategy: ArtifactStrategy | None = None) -> None:
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            "Extract newest video from channel feed",
            component="extract_latest_video",
            event="video.extract",
        ):
            xml = context.get("youtube_feed_xml")
            with context.timed_action():
                video = parse_latest_video(xml)
            context.set("youtube_latest_video", video)
            context.log.log(
                "domain",
                f"Latest video: {video.title}",
                component="extract_latest_video",
                event="video.resolved",
                data={
                    "video_id": video.video_id,
                    "title": video.title,
                    "url": video.url,
                    "published": video.published,
                },
            )


@step("assert_latest_video")
class AssertLatestVideoStep:
    """Confirm newest feed entry looks valid and the watch URL returns 200."""

    def __init__(
        self,
        client: YoutubeChannelClient,
        artifact_strategy: ArtifactStrategy | None = None,
    ) -> None:
        self._client = client
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            "Assert latest video metadata and page status",
            component="assert_latest_video",
            event="video.assert",
        ):
            video: YoutubeVideo = context.get("youtube_latest_video")
            if not video.published:
                raise StepFailedError(self.id, "latest video has no published timestamp")
            status = self._client.get_status(video.url, context)
            if status != 200:
                raise StepFailedError(
                    self.id,
                    f"expected HTTP 200 for latest video ({video.url}), got {status}",
                )
            context.log.log(
                "domain",
                "Latest video page OK",
                component="assert_latest_video",
                event="video.ok",
                data={"status_code": status, "published": video.published},
            )


@step("summarize_latest_video")
class SummarizeLatestVideoStep:
    """Extractive summary from description (LLM summarization comes in Slice 1.4)."""

    def __init__(self, artifact_strategy: ArtifactStrategy | None = None) -> None:
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            "Summarize latest video",
            component="summarize_latest_video",
            event="video.summarize",
        ):
            video: YoutubeVideo = context.get("youtube_latest_video")
            with context.timed_action():
                summary = extractive_summary(video.description, video.title)
            if not summary.strip():
                raise StepFailedError(self.id, "summary is empty")
            context.set("youtube_summary", summary)
            context.log.log(
                "domain",
                "Summary ready",
                component="summarize_latest_video",
                event="video.summary",
                data={"summary": summary, "title": video.title},
            )
