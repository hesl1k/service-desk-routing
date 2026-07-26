from __future__ import annotations

from typing import Any

from app.schemas import ExternalRouteRequest, InternalRouteRequest

LINE_TO_LEVEL = {"L1": 1, "L2": 2, "L3": 3}
PRIORITY_TO_LEVEL = {"low": 1, "medium": 1, "high": 2, "critical": 3}


def to_internal_payload(payload: InternalRouteRequest | ExternalRouteRequest) -> dict[str, Any]:
    if isinstance(payload, InternalRouteRequest):
        return payload.model_dump(mode="json")

    operators = []
    for agent in payload.agents:
        operators.append(
            {
                "id": agent.id,
                "level": LINE_TO_LEVEL[agent.line.value],
                "skills": list(agent.skills),
                "channels": [item.value for item in agent.channels],
                "capacity_min": agent.capacity_minutes,
                "max_chat_slots": max(0, agent.max_concurrent_chats - agent.active_chats),
                "cost_per_minute": agent.cost_per_minute,
                "max_priority": agent.max_priority.value,
            }
        )

    tickets = []
    for ticket in payload.tickets:
        durations = {
            LINE_TO_LEVEL[line.value]: float(minutes)
            for line, minutes in payload.handle_time_minutes[ticket.type].items()
        }
        required_level = PRIORITY_TO_LEVEL[ticket.priority.value]
        default_duration = durations.get(required_level) or durations[min(durations)]
        tickets.append(
            {
                "id": ticket.id,
                "level": required_level,
                "required_skill": ticket.type,
                "channel": ticket.channel.value,
                "duration_min": default_duration,
                "duration_by_level": durations,
                "priority": ticket.priority.value,
                "sla_first_response_min": ticket.sla_first_response_min,
                "sla_resolution_min": ticket.sla_resolution_min,
                "arrival_min": ticket.arrival_min,
            }
        )

    config = payload.config.model_dump(mode="json")
    config["planning_horizon_minutes"] = payload.planning_horizon_minutes
    return {
        "scenario_id": payload.scenario_id,
        "operators": operators,
        "tickets": tickets,
        "config": config,
    }
