"""Local smoke: scenario → run → wait for step projection."""

from __future__ import annotations

import sys
import time

import httpx

API = "http://localhost:8001"


def main() -> int:
    client = httpx.Client(base_url=API, timeout=30.0)
    client.get("/health").raise_for_status()

    tests = client.get("/tests").json()
    if not tests:
        print("FAIL: no tests registered — is the executor running?")
        return 1

    scenario = client.post("/scenarios", json={"name": "e2e", "test_ids": [tests[0]["id"]]}).json()
    run = client.post(f"/scenarios/{scenario['id']}/runs").json()
    print(f"started run {run['id']}")

    deadline = time.time() + 90
    while time.time() < deadline:
        detail = client.get(f"/runs/{run['id']}").json()
        status = detail["status"]
        steps = detail.get("projection", {}).get("steps", [])
        print(f"status={status} steps={len(steps)}")
        if status in {"finished", "failed"}:
            for step in steps:
                print(
                    f"  - {step['name']}: {step['status']} ({step.get('duration_ms')} ms) "
                    f"artifacts={len(step.get('artifacts') or [])}"
                )
            print(
                "scenario_ms=",
                detail.get("projection", {}).get("scenario_duration_ms"),
            )
            if status == "finished" and steps:
                print("PASS")
                return 0
            print("FAIL: unexpected terminal state")
            return 1
        time.sleep(1)

    print("FAIL: timed out waiting for run")
    return 1


if __name__ == "__main__":
    sys.exit(main())
