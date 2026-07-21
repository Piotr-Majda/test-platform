import re

from test_platform_executor.framework.adapters import PageFetcher
from test_platform_executor.framework.artifacts import ArtifactStrategy, NoArtifactStrategy
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.step_decorator import step
from test_platform_executor.framework.steps import StepFailedError


@step("open_page")
class OpenGooglePageStep:
    def __init__(
        self,
        fetcher: PageFetcher,
        url: str = "https://www.google.com",
        artifact_strategy: ArtifactStrategy | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._url = url
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            f"Open page {self._url}",
            component="open_page",
            event="page.open",
            data={"url": self._url},
        ):
            html = self._fetcher.fetch_html(self._url, context)
            context.set("page_html", html)
            context.set("page_url", self._url)
            context.log.log(
                "domain",
                "Page loaded",
                component="open_page",
                event="page.loaded",
                data={"bytes": len(html)},
            )


@step("assert_title")
class AssertTitleContainsStep:
    def __init__(
        self,
        expected: str = "Google",
        artifact_strategy: ArtifactStrategy | None = None,
    ) -> None:
        self._expected = expected
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            f"Assert title contains '{self._expected}'",
            component="assert_title",
            event="title.assert",
            data={"expected": self._expected},
        ):
            html = context.get("page_html")
            with context.timed_action():
                match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
                if match is None:
                    raise StepFailedError(self.id, "page has no <title>")
                title = re.sub(r"\s+", " ", match.group(1)).strip()
                context.set("page_title", title)
                if self._expected.lower() not in title.lower():
                    raise StepFailedError(
                        self.id,
                        f"expected title to contain '{self._expected}', got '{title}'",
                    )
            context.log.log(
                "domain",
                f"Title resolved to '{context.get('page_title')}'",
                component="assert_title",
                event="title.resolved",
                data={"title": context.get("page_title")},
            )
