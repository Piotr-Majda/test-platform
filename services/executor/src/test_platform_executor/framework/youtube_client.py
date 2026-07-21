from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import xml.etree.ElementTree as ET

import httpx

from test_platform_executor.framework.context import StepContext

# AI Engineer — https://www.youtube.com/@aiDotEngineer
AI_ENGINEER_CHANNEL_ID = "UCLKPca3kwwd-B59HNr-_lvA"
CHANNEL_FEED_URL = (
    f"https://www.youtube.com/feeds/videos.xml?channel_id={AI_ENGINEER_CHANNEL_ID}"
)

_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"
_MEDIA = "{http://search.yahoo.com/mrss/}"


@dataclass(frozen=True)
class YoutubeVideo:
    video_id: str
    title: str
    url: str
    published: str
    description: str


class YoutubeChannelClient(Protocol):
    def fetch_feed_xml(self, context: StepContext) -> str: ...

    def get_status(self, url: str, context: StepContext) -> int: ...


class HttpxYoutubeChannelClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        feed_url: str = CHANNEL_FEED_URL,
    ) -> None:
        self._client = client or httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "test-platform-executor/0.1"},
        )
        self._feed_url = feed_url

    def fetch_feed_xml(self, context: StepContext) -> str:
        log = context.log
        with log.scope(
            "adapter",
            "Fetch YouTube channel RSS feed",
            component="youtube_client",
            event="feed.fetch",
            data={"url": self._feed_url},
        ):
            with context.timed_action():
                response = self._client.get(self._feed_url)
            log.log(
                "framework",
                f"feed {response.status_code}",
                component="httpx",
                event="http.response",
                data={"status_code": response.status_code, "bytes": len(response.content)},
            )
            response.raise_for_status()
            return response.text

    def get_status(self, url: str, context: StepContext) -> int:
        log = context.log
        with log.scope(
            "adapter",
            f"GET video page {url}",
            component="youtube_client",
            event="video.get",
            data={"url": url},
        ):
            with context.timed_action():
                response = self._client.get(url)
            log.log(
                "framework",
                f"video page {response.status_code}",
                component="httpx",
                event="http.response",
                data={"status_code": response.status_code, "url": url},
            )
            return response.status_code


class FakeYoutubeChannelClient:
    def __init__(self, feed_xml: str = "", url_status: dict[str, int] | None = None) -> None:
        self.feed_xml = feed_xml
        self.url_status = url_status or {}

    def fetch_feed_xml(self, context: StepContext) -> str:
        with context.timed_action():
            return self.feed_xml

    def get_status(self, url: str, context: StepContext) -> int:
        with context.timed_action():
            if url not in self.url_status:
                raise KeyError(f"no fake status for {url}")
            return self.url_status[url]


def parse_latest_video(feed_xml: str) -> YoutubeVideo:
    root = ET.fromstring(feed_xml)
    entry = root.find(f"{_ATOM}entry")
    if entry is None:
        raise ValueError("YouTube feed has no entries")

    video_id = (entry.findtext(f"{_YT}videoId") or "").strip()
    title = (entry.findtext(f"{_ATOM}title") or "").strip()
    published = (entry.findtext(f"{_ATOM}published") or "").strip()
    link_el = entry.find(f"{_ATOM}link")
    url = (link_el.get("href") if link_el is not None else "") or ""
    if not url and video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"

    description = ""
    media_group = entry.find(f"{_MEDIA}group")
    if media_group is not None:
        description = (media_group.findtext(f"{_MEDIA}description") or "").strip()

    if not video_id or not title or not url:
        raise ValueError("latest video missing video_id, title, or url")

    return YoutubeVideo(
        video_id=video_id,
        title=title,
        url=url,
        published=published,
        description=description,
    )


def extractive_summary(description: str, title: str, *, max_chars: int = 400) -> str:
    """Lightweight summary until Slice 1.4 LLM analysis — prefer description, else title."""
    text = " ".join(description.split()) if description.strip() else title.strip()
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 1].rsplit(" ", 1)[0]
    return clipped + "…"
