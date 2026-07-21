from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from test_platform_executor.framework.context import StepContext

OFFERS_API = "https://justjoin.it/api/candidate-api/offers"
OFFER_PAGE_PREFIX = "https://justjoin.it/job-offer/"


@dataclass(frozen=True)
class JobRole:
    title: str
    url: str


class JustJoinOffersClient(Protocol):
    def fetch_offer_payloads(self, context: StepContext) -> list[dict]: ...

    def get_status(self, url: str, context: StepContext) -> int: ...


class HttpxJustJoinOffersClient:
    """Live JustJoinIT candidate offers API + offer page status checks."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": "test-platform-executor/0.1",
                "Accept": "application/json,text/html",
            },
        )

    def fetch_offer_payloads(self, context: StepContext) -> list[dict]:
        """Paginate python category offers so unique titles can fill a top-10 list."""
        log = context.log
        collected: list[dict] = []
        cursor: int | None = None
        max_pages = 5
        with log.scope(
            "adapter",
            "Fetch JustJoinIT python offers",
            component="justjoin_client",
            event="offers.fetch",
        ):
            for page in range(max_pages):
                params: dict[str, str | int] = {"categories": "python", "itemsCount": 50}
                if cursor is not None:
                    params["from"] = cursor
                with context.timed_action():
                    response = self._client.get(OFFERS_API, params=params)
                log.log(
                    "framework",
                    f"offers API page {page + 1}: {response.status_code}",
                    component="httpx",
                    event="http.response",
                    data={
                        "status_code": response.status_code,
                        "url": str(response.url),
                        "cursor": cursor,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                batch = payload.get("data")
                if not isinstance(batch, list):
                    raise ValueError("JustJoinIT offers response missing data list")
                collected.extend(batch)
                nxt = (payload.get("meta") or {}).get("next") or {}
                cursor = nxt.get("cursor")
                if not cursor or not batch:
                    break
            return collected

    def get_status(self, url: str, context: StepContext) -> int:
        log = context.log
        with log.scope(
            "adapter",
            f"GET offer page {url}",
            component="justjoin_client",
            event="offer.head",
            data={"url": url},
        ):
            with context.timed_action():
                response = self._client.get(url)
            log.log(
                "framework",
                f"offer page {response.status_code}",
                component="httpx",
                event="http.response",
                data={"status_code": response.status_code, "url": url},
            )
            return response.status_code


class FakeJustJoinOffersClient:
    def __init__(
        self,
        offers: list[dict] | None = None,
        url_status: dict[str, int] | None = None,
    ) -> None:
        self.offers = offers or []
        self.url_status = url_status or {}

    def fetch_offer_payloads(self, context: StepContext) -> list[dict]:
        with context.timed_action():
            return list(self.offers)

    def get_status(self, url: str, context: StepContext) -> int:
        with context.timed_action():
            if url not in self.url_status:
                raise KeyError(f"no fake status for {url}")
            return self.url_status[url]


def offer_url_from_slug(slug: str) -> str:
    return f"{OFFER_PAGE_PREFIX}{slug}"
