"""Scoped logger stack — Given / When / Then."""

from test_platform_executor.framework.scoped_log import ScopedLogger


def test_domain_adapter_framework_nesting() -> None:
    log = ScopedLogger(test_id="google_title")
    log.begin_step("open_page")

    with log.scope("domain", "Open page Google", component="open_page", event="page.open"):
        with log.scope(
            "adapter",
            "Open page https://www.google.com",
            component="httpx_page_fetcher",
        ):
            log.log(
                "framework",
                "logs from httpx framework",
                component="httpx",
            )

    document = log.finish_step(failed=False)

    assert document["schema_version"] == "1.0"
    assert document["step_id"] == "open_page"
    domain = document["entries"][0]
    assert domain["layer"] == "domain"
    adapter = domain["children"][0]
    assert adapter["layer"] == "adapter"
    assert adapter["component"] == "httpx_page_fetcher"
    framework = adapter["children"][0]
    assert framework["layer"] == "framework"
    assert "httpx" in framework["message"]
    assert domain["duration_ms"] >= 0


def test_test_document_aggregates_steps() -> None:
    log = ScopedLogger(test_id="google_title")
    log.begin_step("open_page")
    log.log("domain", "a")
    log.finish_step(failed=False)
    log.begin_step("assert_title")
    log.log("domain", "b")
    log.finish_step(failed=False)

    test_doc = log.test_document()

    assert test_doc["test_id"] == "google_title"
    assert test_doc["schema_version"] == "1.0"
    assert [step["step_id"] for step in test_doc["steps"]] == ["open_page", "assert_title"]
