from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Channel(str, Enum):
    chat = "chat"
    email = "email"
    phone = "phone"
    portal = "portal"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SlaMode(str, Enum):
    hard = "hard"
    soft = "soft"


class AgentLine(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class RouteStatus(str, Enum):
    optimal = "optimal"
    infeasible = "infeasible"
    error = "error"


class RouteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_queue: bool = True
    queue_penalty: float = Field(10000.0, ge=0)
    sla_mode: SlaMode = SlaMode.soft
    sla_breach_penalty: float = Field(0.0, ge=0)
    planning_horizon_minutes: float = Field(480.0, gt=0)


class InternalOperator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    level: int = Field(..., ge=1, le=3)
    skills: list[str] = Field(..., min_length=1)
    channels: list[Channel] = Field(..., min_length=1)
    capacity_min: float = Field(..., ge=0)
    max_chat_slots: int = Field(..., ge=0)
    cost_per_minute: float = Field(..., gt=0)
    max_priority: Priority | None = None

    @field_validator("skills")
    @classmethod
    def skills_must_not_contain_blanks(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("skills must not contain blank values")
        return value


class InternalTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    level: int = Field(..., ge=1, le=3)
    required_skill: str | None = None
    channel: Channel
    duration_min: float = Field(..., gt=0)
    duration_by_level: dict[int, float] | None = None
    priority: Priority
    sla_first_response_min: float | None = Field(default=None, gt=0)
    sla_resolution_min: float | None = Field(default=None, gt=0)
    arrival_min: float = Field(default=0.0, ge=0)

    @field_validator("required_skill")
    @classmethod
    def skill_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("required_skill must be null or non-blank")
        return value

    @field_validator("duration_by_level")
    @classmethod
    def durations_must_be_positive(cls, value: dict[int, float] | None) -> dict[int, float] | None:
        if value is None:
            return value
        if any(level not in {1, 2, 3} or minutes <= 0 for level, minutes in value.items()):
            raise ValueError("duration_by_level must contain positive values for levels 1, 2 or 3")
        return value


class InternalRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str | None = None
    scenario_name: str | None = None
    description: str | None = None
    operators: list[InternalOperator] = Field(..., min_length=1)
    tickets: list[InternalTicket] = Field(..., min_length=1)
    config: RouteConfig = Field(default_factory=RouteConfig)

    @model_validator(mode="after")
    def unique_ids(self) -> "InternalRouteRequest":
        _ensure_unique([item.id for item in self.operators], "operator id")
        _ensure_unique([item.id for item in self.tickets], "ticket id")
        return self


class ExternalTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    priority: Priority
    channel: Channel
    sla_first_response_min: float = Field(..., gt=0)
    sla_resolution_min: float = Field(..., gt=0)
    arrival_min: float = Field(default=0.0, ge=0)


class ExternalAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    line: AgentLine
    cost_per_minute: float = Field(..., gt=0)
    skills: list[str] = Field(..., min_length=1)
    max_priority: Priority
    channels: list[Channel] = Field(..., min_length=1)
    capacity_minutes: float = Field(..., ge=0)
    max_concurrent_chats: int = Field(..., ge=0)
    active_chats: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def active_chats_not_above_limit(self) -> "ExternalAgent":
        if self.active_chats > self.max_concurrent_chats:
            raise ValueError("active_chats must not exceed max_concurrent_chats")
        return self


class ExternalRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str | None = None
    planning_horizon_minutes: float = Field(default=480.0, gt=0)
    tickets: list[ExternalTicket] = Field(..., min_length=1)
    agents: list[ExternalAgent] = Field(..., min_length=1)
    handle_time_minutes: dict[str, dict[AgentLine, float]]
    config: RouteConfig = Field(default_factory=RouteConfig)

    @model_validator(mode="after")
    def validate_request(self) -> "ExternalRouteRequest":
        _ensure_unique([item.id for item in self.agents], "agent id")
        _ensure_unique([item.id for item in self.tickets], "ticket id")
        for ticket in self.tickets:
            per_line = self.handle_time_minutes.get(ticket.type)
            if not per_line:
                raise ValueError(f"missing handle_time_minutes for ticket type {ticket.type}")
            if any(minutes <= 0 for minutes in per_line.values()):
                raise ValueError("handle times must be positive")
        return self


RouteRequest = Annotated[Union[InternalRouteRequest, ExternalRouteRequest], Field(union_mode="left_to_right")]


class TicketResult(BaseModel):
    ticket_id: str
    operator_id: str
    operator_level: int = Field(..., ge=1, le=3)
    processing_cost: float = Field(..., ge=0)
    sla_penalty_cost: float = Field(..., ge=0)
    expected_cost: float = Field(..., ge=0)
    expected_handle_time_min: float = Field(..., ge=0)
    start_time_min: float = Field(..., ge=0)
    first_response_time_min: float = Field(..., ge=0)
    resolution_time_min: float = Field(..., ge=0)
    within_sla: bool


class RouteResponse(BaseModel):
    status: RouteStatus
    backend: str
    objective_cost: float = Field(..., ge=0)
    processing_cost: float = Field(..., ge=0)
    penalty_cost: float = Field(..., ge=0)
    queue_penalty_cost: float = Field(..., ge=0)
    sla_penalty_cost: float = Field(..., ge=0)
    assignments: dict[str, list[str]]
    unassigned_ticket_ids: list[str]
    solver_time_ms: float = Field(..., ge=0)
    scenario: str | None = None
    message: str | None = None
    ticket_results: list[TicketResult]


def _ensure_unique(values: list[str], label: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
