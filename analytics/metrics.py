from __future__ import annotations

from statistics import mean
from typing import Any


def summarize_result(scenario: str, method: str, data: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    tickets = {str(item["id"]): item for item in data.get("tickets", [])}
    operators = {str(item["id"]): item for item in data.get("operators", [])}
    rows = result.get("ticket_results", []) or []
    completed = len(rows)
    total = len(tickets)
    unassigned = len(result.get("unassigned_ticket_ids", []) or [])

    used_capacity = {operator_id: 0.0 for operator_id in operators}
    within_sla = 0
    l3 = 0
    afrt_values: list[float] = []
    art_values: list[float] = []
    for row in rows:
        operator_id = str(row["operator_id"])
        used_capacity[operator_id] = used_capacity.get(operator_id, 0.0) + float(row["expected_handle_time_min"])
        within_sla += int(bool(row.get("within_sla", False)))
        l3 += int(int(row.get("operator_level", 0)) == 3)
        afrt_values.append(float(row.get("first_response_time_min", 0.0)))
        art_values.append(float(row.get("resolution_time_min", 0.0)))

    total_capacity = sum(float(item.get("capacity_min", 0.0)) for item in operators.values())
    horizon = float((data.get("config", {}) or {}).get("planning_horizon_minutes", 480.0))

    return {
        "scenario": scenario,
        "method": method,
        "status": result.get("status"),
        "backend": result.get("backend"),
        "total_tickets": total,
        "completed_tickets": completed,
        "unassigned_tickets": unassigned,
        "processing_cost": round(float(result.get("processing_cost", 0.0)), 2),
        "penalty_cost": round(float(result.get("penalty_cost", 0.0)), 2),
        "queue_penalty_cost": round(float(result.get("queue_penalty_cost", 0.0)), 2),
        "sla_penalty_cost": round(float(result.get("sla_penalty_cost", 0.0)), 2),
        "total_cost": round(float(result.get("objective_cost", 0.0)), 2),
        "service_level_percent": round(within_sla / total * 100 if total else 0.0, 2),
        "l3_escalation_rate_percent": round(l3 / completed * 100 if completed else 0.0, 2),
        "utilization_percent": round(sum(used_capacity.values()) / total_capacity * 100 if total_capacity else 0.0, 2),
        "throughput_per_hour": round(completed / horizon * 60 if horizon else 0.0, 2),
        "modeled_afrt_min": round(mean(afrt_values), 2) if afrt_values else 0.0,
        "modeled_art_min": round(mean(art_values), 2) if art_values else 0.0,
        "computation_time_ms": round(float(result.get("solver_time_ms", 0.0)), 2),
    }


def add_savings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["scenario"]), {})[str(row["method"])] = row

    output: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        pair = grouped[str(row["scenario"])]
        if row["method"] == "lp" and "baseline" in pair:
            baseline_cost = float(pair["baseline"]["total_cost"])
            savings = baseline_cost - float(row["total_cost"])
            row["savings"] = round(savings, 2)
            row["savings_percent"] = round(savings / baseline_cost * 100 if baseline_cost else 0.0, 2)
        else:
            row["savings"] = 0.0
            row["savings_percent"] = 0.0
        output.append(row)
    return output


def flatten_ticket_results(scenario: str, method: str, data: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    tickets = {str(item["id"]): item for item in data.get("tickets", [])}
    assigned = {str(item["ticket_id"]): item for item in result.get("ticket_results", []) or []}
    unassigned = set(str(item) for item in result.get("unassigned_ticket_ids", []) or [])
    queue_penalty = float((data.get("config", {}) or {}).get("queue_penalty", 10000.0))
    rows: list[dict[str, Any]] = []
    for ticket_id, ticket in tickets.items():
        row = assigned.get(ticket_id)
        if row:
            rows.append(
                {
                    "scenario": scenario,
                    "method": method,
                    "ticket_id": ticket_id,
                    "priority": ticket.get("priority"),
                    "required_level": ticket.get("level"),
                    "required_skill": ticket.get("required_skill"),
                    "channel": ticket.get("channel"),
                    "assigned_operator_id": row["operator_id"],
                    "assigned_operator_level": row["operator_level"],
                    "status": "assigned",
                    "expected_cost": row["expected_cost"],
                    "expected_handle_time_min": row["expected_handle_time_min"],
                    "first_response_time_min": row["first_response_time_min"],
                    "resolution_time_min": row["resolution_time_min"],
                    "sla_resolution_min": ticket.get("sla_resolution_min"),
                    "within_sla": row["within_sla"],
                    "penalty_cost": float(row.get("sla_penalty_cost", 0.0)),
                }
            )
        else:
            rows.append(
                {
                    "scenario": scenario,
                    "method": method,
                    "ticket_id": ticket_id,
                    "priority": ticket.get("priority"),
                    "required_level": ticket.get("level"),
                    "required_skill": ticket.get("required_skill"),
                    "channel": ticket.get("channel"),
                    "assigned_operator_id": "",
                    "assigned_operator_level": "",
                    "status": "unassigned" if ticket_id in unassigned else "missing",
                    "expected_cost": 0.0,
                    "expected_handle_time_min": 0.0,
                    "first_response_time_min": 0.0,
                    "resolution_time_min": 0.0,
                    "sla_resolution_min": ticket.get("sla_resolution_min"),
                    "within_sla": False,
                    "penalty_cost": queue_penalty,
                }
            )
    return rows
