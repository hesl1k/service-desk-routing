from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from locust import HttpUser, between, task

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT / "data" / "scenarios"


def load_payloads() -> list[dict[str, Any]]:
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(SCENARIO_DIR.glob("*.json"))]
    if not payloads:
        raise RuntimeError(f"No scenarios found in {SCENARIO_DIR}")
    return payloads


PAYLOADS = load_payloads()


class RouteApiUser(HttpUser):
    wait_time = between(0.01, 0.2)

    @task(10)
    def route(self) -> None:
        with self.client.post("/route", json=random.choice(PAYLOADS), name="POST /route", catch_response=True, timeout=30) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}: {response.text[:200]}")
                return
            try:
                body = response.json()
            except ValueError:
                response.failure("response is not JSON")
                return
            if body.get("status") not in {"optimal", "infeasible"}:
                response.failure(str(body.get("message") or body.get("status")))
                return
            response.success()

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="GET /health", timeout=5)
