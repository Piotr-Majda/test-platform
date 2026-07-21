from typing import Protocol

import httpx

from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.scoped_log import ScopedLogger


class PageFetcher(Protocol):
    def fetch_html(self, url: str, context: StepContext) -> str: ...


class HttpxPageFetcher:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(follow_redirects=True, timeout=30.0)

    def fetch_html(self, url: str, context: StepContext) -> str:
        log: ScopedLogger = context.log
        with log.scope(
            "adapter",
            f"Open page {url}",
            component="httpx_page_fetcher",
            event="page.fetch",
            data={"url": url},
        ):
            with log.scope(
                "framework",
                "httpx GET request",
                component="httpx",
                event="http.request",
                data={"method": "GET", "url": url},
            ):
                with context.timed_action():
                    response = self._client.get(url)
                log.log(
                    "framework",
                    f"httpx response {response.status_code}",
                    component="httpx",
                    event="http.response",
                    data={
                        "status_code": response.status_code,
                        "bytes": len(response.content),
                        "url": str(response.url),
                    },
                )
                response.raise_for_status()
                return response.text


class FakePageFetcher:
    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.pages = pages or {}

    def fetch_html(self, url: str, context: StepContext) -> str:
        log = context.log
        with log.scope(
            "adapter",
            f"Open page {url}",
            component="fake_page_fetcher",
            event="page.fetch",
            data={"url": url},
        ):
            with context.timed_action():
                if url not in self.pages:
                    raise KeyError(f"no fake page for {url}")
                html = self.pages[url]
            log.log(
                "framework",
                "fake response 200",
                component="fake_http",
                event="http.response",
                data={"status_code": 200, "url": url},
            )
            return html
