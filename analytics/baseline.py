from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from app.domain import PRIORITY_RANK, build_schedule, duration_for, operator_can_handle


def solve_baseline(data: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    tickets = sorted(
        deepcopy(data.get("tickets", [])),
        key=lambda item: (
            PRIORITY_RANK.get(str(item.get("priority", "medium")), 2),
            float(item.get("sla_resolution_min") or 10**12),
            float(item.get("arrival_min", 0.0)),
            str(item.get("id")),
        ),
    )
    operators = deepcopy(data.get("operators", []))
    config = data.get("config", {}) or {}
    queue_penalty = float(config.get("queue_penalty", 10000.0))
    sla_penalty_value = float(config.get("sla_breach_penalty", 0.0))

    used = {str(item["id"]): 0.0 for item in operators}
    chat_used = {str(item["id"]): 0 for item in operators}
    assignments = {str(item["id"]): [] for item in operators}
    ticket_results: list[dict[str, Any]] = []
    unassigned: list[str] = []
    processing_cost = 0.0
    sla_penalty_cost = 0.0

    for ticket in tickets:
        candidates = []
        for operator in operators:
            operator_id = str(operator["id"])
            duration = duration_for(ticket, operator)
            if not operator_can_handle(ticket, operator):
                continue
            if used[operator_id] + duration > float(operator.get("capacity_min", 0.0)):
                continue
            if ticket.get("channel") == "chat" and chat_used[operator_id] + 1 > int(operator.get("max_chat_slots", 0)):
                continue
            if str(config.get("sla_mode", "soft")) == "hard":
                sla = ticket.get("sla_resolution_min")
                if sla is not None and duration > float(sla):
                    continue
            candidates.append(operator)

        if not candidates:
            unassigned.append(str(ticket["id"]))
            continue

        candidates.sort(
            key=lambda operator: (
                int(operator.get("level", 1)),
                -(float(operator.get("capacity_min", 0.0)) - used[str(operator["id"])]),
                str(operator["id"]),
            )
        )
        operator = candidates[0]
        operator_id = str(operator["id"])
        duration = duration_for(ticket, operator)
        processing = duration * float(operator.get("cost_per_minute", 0.0))
        sla = ticket.get("sla_resolution_min")
        assignment_sla_penalty = (
            sla_penalty_value
            if str(config.get("sla_mode", "soft")) == "soft" and sla is not None and duration > float(sla)
            else 0.0
        )
        processing_cost += processing
        sla_penalty_cost += assignment_sla_penalty
        used[operator_id] += duration
        if ticket.get("channel") == "chat":
            chat_used[operator_id] += 1
        assignments[operator_id].append(str(ticket["id"]))
        ticket_results.append(
            {
                "ticket_id": str(ticket["id"]),
                "operator_id": operator_id,
                "processing_cost": round(processing, 2),
                "sla_penalty_cost": round(assignment_sla_penalty, 2),
                "expected_cost": round(processing + assignment_sla_penalty, 2),
            }
        )

    scheduled = build_schedule(data, ticket_results)
    queue_penalty_cost = len(unassigned) * queue_penalty
    return {
        "status": "completed",
        "backend": "baseline-heuristic",
        "objective_cost": round(processing_cost + sla_penalty_cost + queue_penalty_cost, 2),
        "processing_cost": round(processing_cost, 2),
        "penalty_cost": round(sla_penalty_cost + queue_penalty_cost, 2),
        "queue_penalty_cost": round(queue_penalty_cost, 2),
        "sla_penalty_cost": round(sla_penalty_cost, 2),
        "assignments": {key: value for key, value in assignments.items() if value},
        "unassigned_ticket_ids": unassigned,
        "solver_time_ms": round((time.perf_counter() - started) * 1000, 2),
        "scenario": data.get("scenario_id"),
        "message": None,
        "ticket_results": scheduled,
    }
