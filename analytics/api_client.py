from __future__ import annotations

from typing import Any

import httpx


def call_route_api(data: dict[str, Any], base_url: str, timeout: float = 30.0) -> dict[str, Any]:
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        response = client.post("/route", json=data)
        response.raise_for_status()
        result = response.json()
    if result.get("status") == "error":
        raise RuntimeError(result.get("message") or "route API returned an error")
    return result
