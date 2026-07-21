"""JustJoinIT python roles — Given / When / Then."""

import pytest
from test_platform_contracts import TestRunEventType

from test_platform_executor.events import InMemoryProgressPublisher
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.emission import set_emission_context
from test_platform_executor.framework.justjoin_client import FakeJustJoinOffersClient, offer_url_from_slug
from test_platform_executor.framework.justjoin_steps import (
    AssertOfferUrlsStep,
    ExtractPythonRolesStep,
    FetchPythonOffersStep,
    select_python_roles,
)
from test_platform_executor.framework.steps import StepFailedError


@pytest.fixture(autouse=True)
def emission() -> InMemoryProgressPublisher:
    publisher = InMemoryProgressPublisher()
    set_emission_context(emitter=publisher.publish, run_id="run-jjit", test_id="justjoin_python_roles")
    return publisher


def _python_offers(n: int = 12) -> list[dict]:
    return [
        {
            "title": f"Python Developer {i}",
            "slug": f"acme-python-developer-{i}--warszawa-python",
            "category": {"key": "python"},
        }
        for i in range(n)
    ]


def test_select_python_roles_keeps_python_titles_only() -> None:
    payloads = [
        {"title": "Java Engineer", "slug": "x-java"},
        {"title": "Senior Python Backend", "slug": "x-python"},
        {"title": "IT Manager", "slug": "y-python"},
        {"title": "Python Data Engineer", "slug": "z-python"},
    ]

    roles = select_python_roles(payloads, limit=10)

    assert [r.title for r in roles] == ["Senior Python Backend", "Python Data Engineer"]
    assert roles[0].url == offer_url_from_slug("x-python")


def test_select_python_roles_skips_duplicate_titles_other_cities() -> None:
    payloads = [
        {"title": "Senior Full Stack Engineer (Python + React + SQL)", "slug": "epam--warsaw-python"},
        {"title": "Senior Full Stack Engineer (Python + React + SQL)", "slug": "epam--gdansk-python"},
        {"title": "Python Developer", "slug": "acme--warszawa-python"},
        {"title": "  senior full stack engineer (python + react + sql) ", "slug": "epam--wroclaw-python"},
    ]

    roles = select_python_roles(payloads, limit=10)

    assert [r.title for r in roles] == [
        "Senior Full Stack Engineer (Python + React + SQL)",
        "Python Developer",
    ]
    assert roles[0].url.endswith("epam--warsaw-python")


def test_extract_requires_ten_python_roles() -> None:
    context = StepContext()
    context.set("jjit_offer_payloads", _python_offers(5))

    with pytest.raises(StepFailedError, match="at least 10"):
        ExtractPythonRolesStep(limit=10).execute(context)


def test_happy_path_fetch_extract_and_check_first_three_urls(
    emission: InMemoryProgressPublisher,
) -> None:
    offers = _python_offers(10)
    urls = {
        offer_url_from_slug(o["slug"]): 200
        for o in offers[:3]
    }
    client = FakeJustJoinOffersClient(offers=offers, url_status=urls)
    context = StepContext()

    FetchPythonOffersStep(client).execute(context)
    ExtractPythonRolesStep(limit=10).execute(context)
    AssertOfferUrlsStep(client, check_count=3).execute(context)

    roles = context.get("jjit_roles")
    assert len(roles) == 10
    assert all("python" in r.title.lower() for r in roles)
    finished = [e for e in emission.events if e.event_type == TestRunEventType.STEP_FINISHED]
    assert {e.step_id for e in finished} == {
        "fetch_python_offers",
        "extract_python_roles",
        "assert_offer_urls",
    }


def test_assert_offer_urls_fails_when_status_not_200() -> None:
    offers = _python_offers(10)
    bad = offer_url_from_slug(offers[0]["slug"])
    client = FakeJustJoinOffersClient(
        offers=offers,
        url_status={
            bad: 404,
            offer_url_from_slug(offers[1]["slug"]): 200,
            offer_url_from_slug(offers[2]["slug"]): 200,
        },
    )
    context = StepContext()
    context.set("jjit_offer_payloads", offers)
    ExtractPythonRolesStep(limit=10).execute(context)

    with pytest.raises(StepFailedError, match="404"):
        AssertOfferUrlsStep(client, check_count=3).execute(context)
