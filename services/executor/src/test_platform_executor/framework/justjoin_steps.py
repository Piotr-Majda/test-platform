from __future__ import annotations

import re

from test_platform_executor.framework.artifacts import ArtifactStrategy, NoArtifactStrategy
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.justjoin_client import (
    JobRole,
    JustJoinOffersClient,
    offer_url_from_slug,
)
from test_platform_executor.framework.step_decorator import step
from test_platform_executor.framework.steps import StepFailedError

_PYTHON_IN_TITLE = re.compile(r"python", re.IGNORECASE)


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def select_python_roles(payloads: list[dict], *, limit: int = 10) -> list[JobRole]:
    """Python-related titles + url; skip duplicate titles (same role, other cities)."""
    roles: list[JobRole] = []
    seen_titles: set[str] = set()
    for item in payloads:
        title = str(item.get("title") or "").strip()
        slug = str(item.get("slug") or "").strip()
        if not title or not slug:
            continue
        if _PYTHON_IN_TITLE.search(title) is None:
            continue
        key = _normalize_title(title)
        if key in seen_titles:
            continue
        seen_titles.add(key)
        roles.append(JobRole(title=title, url=offer_url_from_slug(slug)))
        if len(roles) >= limit:
            break
    return roles


@step("fetch_python_offers")
class FetchPythonOffersStep:
    def __init__(
        self,
        client: JustJoinOffersClient,
        artifact_strategy: ArtifactStrategy | None = None,
    ) -> None:
        self._client = client
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            "Fetch JustJoinIT python category offers",
            component="fetch_python_offers",
            event="offers.fetch",
        ):
            payloads = self._client.fetch_offer_payloads(context)
            context.set("jjit_offer_payloads", payloads)
            context.log.log(
                "domain",
                f"Loaded {len(payloads)} offer payloads",
                component="fetch_python_offers",
                event="offers.loaded",
                data={"count": len(payloads)},
            )


@step("extract_python_roles")
class ExtractPythonRolesStep:
    def __init__(
        self,
        *,
        limit: int = 10,
        artifact_strategy: ArtifactStrategy | None = None,
    ) -> None:
        self._limit = limit
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            f"Extract {self._limit} Python-related roles",
            component="extract_python_roles",
            event="roles.extract",
            data={"limit": self._limit},
        ):
            payloads = context.get("jjit_offer_payloads")
            with context.timed_action():
                roles = select_python_roles(payloads, limit=self._limit)
            if len(roles) < self._limit:
                raise StepFailedError(
                    self.id,
                    f"expected at least {self._limit} Python-related roles, got {len(roles)}",
                )
            context.set("jjit_roles", roles)
            context.log.log(
                "domain",
                f"Selected {len(roles)} roles",
                component="extract_python_roles",
                event="roles.selected",
                data={"titles": [r.title for r in roles]},
            )


@step("assert_offer_urls")
class AssertOfferUrlsStep:
    """GET the first N role URLs and require HTTP 200."""

    def __init__(
        self,
        client: JustJoinOffersClient,
        *,
        check_count: int = 3,
        artifact_strategy: ArtifactStrategy | None = None,
    ) -> None:
        self._client = client
        self._check_count = check_count
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            f"Assert first {self._check_count} offer URLs return 200",
            component="assert_offer_urls",
            event="urls.assert",
            data={"check_count": self._check_count},
        ):
            roles: list[JobRole] = context.get("jjit_roles")
            sample = roles[: self._check_count]
            if len(sample) < self._check_count:
                raise StepFailedError(
                    self.id,
                    f"need at least {self._check_count} roles to check URLs, got {len(sample)}",
                )
            for role in sample:
                status = self._client.get_status(role.url, context)
                if status != 200:
                    raise StepFailedError(
                        self.id,
                        f"expected HTTP 200 for '{role.title}' ({role.url}), got {status}",
                    )
            context.log.log(
                "domain",
                f"Checked {len(sample)} offer URLs OK",
                component="assert_offer_urls",
                event="urls.ok",
                data={"urls": [r.url for r in sample]},
            )
