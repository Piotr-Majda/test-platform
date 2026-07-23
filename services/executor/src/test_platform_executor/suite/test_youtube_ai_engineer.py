import os

import pytest

from test_platform_executor.framework.artifacts import HtmlSnapshotArtifactStrategy, create_artifact_store
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import get_run_id, get_test_id
from test_platform_executor.framework.scoped_log import ScopedLogger
from test_platform_executor.framework.youtube_client import (
    FakeYoutubeChannelClient,
    HttpxYoutubeChannelClient,
)
from test_platform_executor.framework.youtube_steps import (
    AssertLatestVideoMetadataStep,
    ExtractLatestVideoStep,
    FetchChannelFeedStep,
    SummarizeLatestVideoStep,
)
from test_platform_executor.paths import artifacts_dir

_FAKE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <yt:videoId>fakeVideo1</yt:videoId>
  <title>Fake AI Engineer Talk</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=fakeVideo1"/>
  <published>2026-07-01T00:00:00+00:00</published>
  <media:group>
   <media:description>Fake description about agents and evaluation for unit/CI runs.</media:description>
  </media:group>
 </entry>
</feed>
"""


def _client():
    if os.getenv("PLATFORM_FAKE_YOUTUBE") == "1":
        return FakeYoutubeChannelClient(feed_xml=_FAKE_FEED)
    return HttpxYoutubeChannelClient()


@pytest.mark.platform_test("youtube_ai_engineer_latest")
def test_youtube_ai_engineer_latest(platform_emitter) -> None:
    store = create_artifact_store(artifacts_dir(), get_run_id())
    strategy = HtmlSnapshotArtifactStrategy(store)
    client = _client()
    context = StepContext(log=ScopedLogger(test_id=get_test_id()))

    FetchChannelFeedStep(client, artifact_strategy=strategy).execute(context)
    ExtractLatestVideoStep(artifact_strategy=strategy).execute(context)
    AssertLatestVideoMetadataStep(artifact_strategy=strategy).execute(context)
    SummarizeLatestVideoStep(artifact_strategy=strategy).execute(context)
