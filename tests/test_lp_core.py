from __future__ import annotations

import json
from pathlib import Path

from analytics.baseline import solve_baseline
from app.lp_core import solve_lp

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "data" / "scenarios" / name).read_text(encoding="utf-8"))


def test_lp_returns_complete_result() -> None:
    result = solve_lp(load("normal_load.json"))
    assert result["status"] == "optimal"
    assert result["backend"] in {"scipy-milp", "pulp-cbc"}
    assert result["objective_cost"] == result["processing_cost"] + result["penalty_cost"]
    assert len(result["ticket_results"]) + len(result["unassigned_ticket_ids"]) == 6
    for row in result["ticket_results"]:
        assert row["resolution_time_min"] >= row["expected_handle_time_min"]
        assert 1 <= row["operator_level"] <= 3


def test_lp_is_not_more_expensive_than_baseline() -> None:
    for path in sorted((ROOT / "data" / "scenarios").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        baseline = solve_baseline(data)
        lp = solve_lp(data)
        assert lp["status"] == "optimal"
        assert lp["objective_cost"] <= baseline["objective_cost"] + 1e-6


def test_queue_disabled_can_be_infeasible() -> None:
    data = {
        "operators": [{"id": "O1", "level": 1, "skills": ["question"], "channels": ["email"], "capacity_min": 10, "max_chat_slots": 0, "cost_per_minute": 1}],
        "tickets": [{"id": "T1", "level": 3, "required_skill": "incident", "channel": "chat", "duration_min": 20, "priority": "critical"}],
        "config": {"allow_queue": False, "queue_penalty": 10000, "planning_horizon_minutes": 60},
    }
    result = solve_lp(data)
    assert result["status"] == "infeasible"
