from __future__ import annotations

from collections import defaultdict
from typing import Any

PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
PRIORITY_MAX_RANK = {"low": 3, "medium": 2, "high": 1, "critical": 0}


def duration_for(ticket: dict[str, Any], operator: dict[str, Any]) -> float:
    durations = ticket.get("duration_by_level") or {}
    level = int(operator.get("level", 1))
    value = durations.get(level)
    if value is None:
        value = durations.get(str(level))
    return float(value if value is not None else ticket.get("duration_min", 0.0))


def operator_can_handle(ticket: dict[str, Any], operator: dict[str, Any]) -> bool:
    if int(operator.get("level", 1)) < int(ticket.get("level", 1)):
        return False
    skill = ticket.get("required_skill")
    if skill and skill not in (operator.get("skills") or []):
        return False
    channel = ticket.get("channel")
    if channel and channel not in (operator.get("channels") or []):
        return False
    max_priority = operator.get("max_priority")
    if max_priority:
        ticket_rank = PRIORITY_RANK.get(str(ticket.get("priority", "medium")), 2)
        max_rank = PRIORITY_RANK.get(str(max_priority), 2)
        if ticket_rank < max_rank:
            return False
    return True


def build_schedule(
    data: dict[str, Any],
    ticket_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tickets = {str(item["id"]): item for item in data.get("tickets", [])}
    operators = {str(item["id"]): item for item in data.get("operators", [])}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ticket_results:
        grouped[str(row["operator_id"])].append(dict(row))

    scheduled: list[dict[str, Any]] = []
    for operator_id, rows in grouped.items():
        operator = operators[operator_id]
        rows.sort(
            key=lambda row: (
                PRIORITY_RANK.get(str(tickets[str(row["ticket_id"])].get("priority", "medium")), 2),
                float(tickets[str(row["ticket_id"])].get("sla_resolution_min") or 10**12),
                float(tickets[str(row["ticket_id"])].get("arrival_min", 0.0)),
                str(row["ticket_id"]),
            )
        )
        next_free = 0.0
        for row in rows:
            ticket = tickets[str(row["ticket_id"])]
            arrival = float(ticket.get("arrival_min", 0.0))
            start = max(next_free, arrival)
            duration = duration_for(ticket, operator)
            resolution = start + duration - arrival
            first_response = start - arrival
            sla = ticket.get("sla_resolution_min")
            within_sla = True if sla is None else resolution <= float(sla)
            row.update(
                {
                    "operator_level": int(operator.get("level", 1)),
                    "expected_handle_time_min": round(duration, 2),
                    "start_time_min": round(start, 2),
                    "first_response_time_min": round(first_response, 2),
                    "resolution_time_min": round(resolution, 2),
                    "within_sla": bool(within_sla),
                }
            )
            scheduled.append(row)
            next_free = start + duration
    return sorted(scheduled, key=lambda row: str(row["ticket_id"]))
