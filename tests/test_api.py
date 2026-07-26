from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_internal_route() -> None:
    payload = json.loads((ROOT / "data" / "scenarios" / "normal_load.json").read_text(encoding="utf-8"))
    response = client.post("/route", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "optimal"
    assert body["ticket_results"]
    assert body["processing_cost"] >= 0


def test_external_route() -> None:
    payload = {
        "planning_horizon_minutes": 60,
        "tickets": [{"id": "T1", "type": "incident", "priority": "high", "channel": "chat", "sla_first_response_min": 15, "sla_resolution_min": 120}],
        "agents": [{"id": "A1", "line": "L2", "cost_per_minute": 8, "skills": ["incident"], "max_priority": "critical", "channels": ["chat"], "capacity_minutes": 60, "max_concurrent_chats": 1, "active_chats": 0}],
        "handle_time_minutes": {"incident": {"L2": 25}},
        "config": {"allow_queue": True, "queue_penalty": 10000, "sla_mode": "soft", "sla_breach_penalty": 0, "planning_horizon_minutes": 60},
    }
    response = client.post("/route", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["assignments"] == {"A1": ["T1"]}
    assert body["ticket_results"][0]["expected_handle_time_min"] == 25


def test_invalid_payload_returns_422_envelope() -> None:
    response = client.post("/route", json={"tickets": []})
    assert response.status_code == 422
    assert response.json()["status"] == "error"
