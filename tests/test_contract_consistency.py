from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.lp_core import solve_lp
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_direct_and_api_results_match() -> None:
    payload = json.loads((ROOT / "data" / "scenarios" / "peak_hours.json").read_text(encoding="utf-8"))
    direct = solve_lp(payload)
    via_api = client.post("/route", json=payload).json()
    for field in ["status", "objective_cost", "processing_cost", "penalty_cost", "assignments", "unassigned_ticket_ids"]:
        assert via_api[field] == direct[field]
