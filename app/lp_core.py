from __future__ import annotations

import importlib.util
import math
import os
import time
from typing import Any

from app.domain import build_schedule, duration_for, operator_can_handle


def solve_lp(data: dict[str, Any]) -> dict[str, Any]:
    """Solve the Service Desk assignment model.

    The function uses PuLP/CBC when PuLP is installed. In environments without
    PuLP it uses scipy.optimize.milp with the same variables and constraints.
    """
    started = time.perf_counter()
    try:
        _validate_data(data)
        requested_backend = os.getenv("LP_BACKEND", "scipy").strip().lower()
        if requested_backend == "pulp":
            if importlib.util.find_spec("pulp") is None:
                raise RuntimeError("LP_BACKEND=pulp, but PuLP is not installed")
            result = _solve_with_pulp(data)
        elif requested_backend == "scipy":
            if importlib.util.find_spec("scipy") is not None:
                result = _solve_with_scipy(data)
            elif importlib.util.find_spec("pulp") is not None:
                result = _solve_with_pulp(data)
            else:
                raise RuntimeError("neither SciPy nor PuLP is installed")
        else:
            raise ValueError("LP_BACKEND must be 'scipy' or 'pulp'")
    except Exception as exc:
        return _empty_result(
            status="error",
            backend="none",
            solver_time_ms=(time.perf_counter() - started) * 1000,
            message=str(exc),
        )
    result["solver_time_ms"] = round((time.perf_counter() - started) * 1000, 2)
    result["scenario"] = data.get("scenario_id")
    return result


def _validate_data(data: dict[str, Any]) -> None:
    tickets = data.get("tickets")
    operators = data.get("operators")
    if not isinstance(tickets, list) or not tickets:
        raise ValueError("tickets must be a non-empty list")
    if not isinstance(operators, list) or not operators:
        raise ValueError("operators must be a non-empty list")
    ticket_ids = [str(item["id"]) for item in tickets]
    operator_ids = [str(item["id"]) for item in operators]
    if len(ticket_ids) != len(set(ticket_ids)):
        raise ValueError("ticket ids must be unique")
    if len(operator_ids) != len(set(operator_ids)):
        raise ValueError("operator ids must be unique")


def _pair_cost(
    ticket: dict[str, Any],
    operator: dict[str, Any],
    config: dict[str, Any],
) -> tuple[float, float, float]:
    duration = duration_for(ticket, operator)
    processing = duration * float(operator.get("cost_per_minute", 0.0))
    sla_penalty = 0.0
    sla = ticket.get("sla_resolution_min")
    if sla is not None and duration > float(sla):
        if str(config.get("sla_mode", "soft")) == "hard":
            return duration, processing, float("inf")
        sla_penalty = float(config.get("sla_breach_penalty", 0.0))
    return duration, processing, sla_penalty


def _solve_with_scipy(data: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp

    tickets = data["tickets"]
    operators = data["operators"]
    config = data.get("config", {}) or {}
    allow_queue = bool(config.get("allow_queue", True))
    queue_penalty = float(config.get("queue_penalty", 10000.0))

    n_tickets = len(tickets)
    n_operators = len(operators)
    n_pairs = n_tickets * n_operators
    n_vars = n_pairs + n_tickets

    def x_index(ticket_index: int, operator_index: int) -> int:
        return ticket_index * n_operators + operator_index

    def u_index(ticket_index: int) -> int:
        return n_pairs + ticket_index

    c = np.zeros(n_vars, dtype=float)
    lower = np.zeros(n_vars, dtype=float)
    upper = np.ones(n_vars, dtype=float)
    pair_meta: dict[tuple[int, int], tuple[float, float, float]] = {}

    for i, ticket in enumerate(tickets):
        for j, operator in enumerate(operators):
            idx = x_index(i, j)
            duration, processing, sla_penalty = _pair_cost(ticket, operator, config)
            pair_meta[i, j] = (duration, processing, sla_penalty)
            if not operator_can_handle(ticket, operator) or not math.isfinite(sla_penalty):
                upper[idx] = 0.0
                c[idx] = 0.0
            else:
                c[idx] = processing + sla_penalty
        c[u_index(i)] = queue_penalty
        if not allow_queue:
            upper[u_index(i)] = 0.0

    rows: list[np.ndarray] = []
    lows: list[float] = []
    highs: list[float] = []

    for i in range(n_tickets):
        row = np.zeros(n_vars, dtype=float)
        for j in range(n_operators):
            row[x_index(i, j)] = 1.0
        row[u_index(i)] = 1.0
        rows.append(row)
        lows.append(1.0)
        highs.append(1.0)

    for j, operator in enumerate(operators):
        row = np.zeros(n_vars, dtype=float)
        for i in range(n_tickets):
            row[x_index(i, j)] = pair_meta[i, j][0]
        rows.append(row)
        lows.append(-np.inf)
        highs.append(float(operator.get("capacity_min", 0.0)))

        chat_row = np.zeros(n_vars, dtype=float)
        for i, ticket in enumerate(tickets):
            if ticket.get("channel") == "chat":
                chat_row[x_index(i, j)] = 1.0
        rows.append(chat_row)
        lows.append(-np.inf)
        highs.append(float(operator.get("max_chat_slots", 0)))

    constraint = LinearConstraint(np.vstack(rows), np.asarray(lows), np.asarray(highs))
    result = milp(
        c=c,
        integrality=np.ones(n_vars, dtype=int),
        bounds=Bounds(lower, upper),
        constraints=constraint,
        options={"disp": False},
    )
    if not result.success or result.x is None:
        return _empty_result(
            status="infeasible",
            backend="scipy-milp",
            solver_time_ms=0.0,
            message=result.message,
            unassigned=[str(item["id"]) for item in tickets],
        )

    assignments: dict[str, list[str]] = {str(item["id"]): [] for item in operators}
    ticket_results: list[dict[str, Any]] = []
    unassigned: list[str] = []
    processing_cost = 0.0
    sla_penalty_cost = 0.0

    for i, ticket in enumerate(tickets):
        assigned = False
        for j, operator in enumerate(operators):
            if result.x[x_index(i, j)] > 0.5:
                duration, processing, sla_penalty = pair_meta[i, j]
                operator_id = str(operator["id"])
                ticket_id = str(ticket["id"])
                assignments[operator_id].append(ticket_id)
                processing_cost += processing
                sla_penalty_cost += sla_penalty
                ticket_results.append(
                    {
                        "ticket_id": ticket_id,
                        "operator_id": operator_id,
                        "processing_cost": round(processing, 2),
                        "sla_penalty_cost": round(sla_penalty, 2),
                        "expected_cost": round(processing + sla_penalty, 2),
                    }
                )
                assigned = True
                break
        if not assigned:
            unassigned.append(str(ticket["id"]))

    return _finalize_result(
        data=data,
        backend="scipy-milp",
        assignments=assignments,
        ticket_results=ticket_results,
        unassigned=unassigned,
        processing_cost=processing_cost,
        sla_penalty_cost=sla_penalty_cost,
        queue_penalty=len(unassigned) * queue_penalty,
    )


def _solve_with_pulp(data: dict[str, Any]) -> dict[str, Any]:
    import pulp

    tickets = data["tickets"]
    operators = data["operators"]
    config = data.get("config", {}) or {}
    allow_queue = bool(config.get("allow_queue", True))
    queue_penalty = float(config.get("queue_penalty", 10000.0))

    problem = pulp.LpProblem("ServiceDeskRouting", pulp.LpMinimize)
    x: dict[tuple[int, int], Any] = {}
    u: dict[int, Any] = {}
    pair_meta: dict[tuple[int, int], tuple[float, float, float]] = {}

    for i, ticket in enumerate(tickets):
        u[i] = pulp.LpVariable(f"u_{i}", lowBound=0, upBound=1, cat="Binary")
        for j, operator in enumerate(operators):
            x[i, j] = pulp.LpVariable(f"x_{i}_{j}", lowBound=0, upBound=1, cat="Binary")
            pair_meta[i, j] = _pair_cost(ticket, operator, config)

    objective = []
    for i, ticket in enumerate(tickets):
        objective.append(queue_penalty * u[i])
        for j, operator in enumerate(operators):
            duration, processing, sla_penalty = pair_meta[i, j]
            objective.append((processing + (0 if not math.isfinite(sla_penalty) else sla_penalty)) * x[i, j])
            if not operator_can_handle(ticket, operator) or not math.isfinite(sla_penalty):
                problem += x[i, j] == 0
    problem += pulp.lpSum(objective)

    for i in range(len(tickets)):
        problem += pulp.lpSum(x[i, j] for j in range(len(operators))) + u[i] == 1
        if not allow_queue:
            problem += u[i] == 0

    for j, operator in enumerate(operators):
        problem += pulp.lpSum(pair_meta[i, j][0] * x[i, j] for i in range(len(tickets))) <= float(operator.get("capacity_min", 0.0))
        problem += pulp.lpSum(x[i, j] for i, ticket in enumerate(tickets) if ticket.get("channel") == "chat") <= int(operator.get("max_chat_slots", 0))

    problem.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[problem.status] != "Optimal":
        return _empty_result(
            status="infeasible",
            backend="pulp-cbc",
            solver_time_ms=0.0,
            message=pulp.LpStatus[problem.status],
            unassigned=[str(item["id"]) for item in tickets],
        )

    assignments: dict[str, list[str]] = {str(item["id"]): [] for item in operators}
    ticket_results: list[dict[str, Any]] = []
    unassigned: list[str] = []
    processing_cost = 0.0
    sla_penalty_cost = 0.0

    for i, ticket in enumerate(tickets):
        assigned = False
        for j, operator in enumerate(operators):
            if pulp.value(x[i, j]) > 0.5:
                duration, processing, sla_penalty = pair_meta[i, j]
                operator_id = str(operator["id"])
                ticket_id = str(ticket["id"])
                assignments[operator_id].append(ticket_id)
                processing_cost += processing
                sla_penalty_cost += sla_penalty
                ticket_results.append(
                    {
                        "ticket_id": ticket_id,
                        "operator_id": operator_id,
                        "processing_cost": round(processing, 2),
                        "sla_penalty_cost": round(sla_penalty, 2),
                        "expected_cost": round(processing + sla_penalty, 2),
                    }
                )
                assigned = True
                break
        if not assigned:
            unassigned.append(str(ticket["id"]))

    return _finalize_result(
        data=data,
        backend="pulp-cbc",
        assignments=assignments,
        ticket_results=ticket_results,
        unassigned=unassigned,
        processing_cost=processing_cost,
        sla_penalty_cost=sla_penalty_cost,
        queue_penalty=len(unassigned) * queue_penalty,
    )


def _finalize_result(
    *,
    data: dict[str, Any],
    backend: str,
    assignments: dict[str, list[str]],
    ticket_results: list[dict[str, Any]],
    unassigned: list[str],
    processing_cost: float,
    sla_penalty_cost: float,
    queue_penalty: float,
) -> dict[str, Any]:
    scheduled = build_schedule(data, ticket_results)
    return {
        "status": "optimal",
        "backend": backend,
        "objective_cost": round(processing_cost + sla_penalty_cost + queue_penalty, 2),
        "processing_cost": round(processing_cost, 2),
        "penalty_cost": round(sla_penalty_cost + queue_penalty, 2),
        "queue_penalty_cost": round(queue_penalty, 2),
        "sla_penalty_cost": round(sla_penalty_cost, 2),
        "assignments": {key: value for key, value in assignments.items() if value},
        "unassigned_ticket_ids": unassigned,
        "solver_time_ms": 0.0,
        "scenario": data.get("scenario_id"),
        "message": None,
        "ticket_results": scheduled,
    }


def _empty_result(
    *,
    status: str,
    backend: str,
    solver_time_ms: float,
    message: str | None,
    unassigned: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "backend": backend,
        "objective_cost": 0.0,
        "processing_cost": 0.0,
        "penalty_cost": 0.0,
        "queue_penalty_cost": 0.0,
        "sla_penalty_cost": 0.0,
        "assignments": {},
        "unassigned_ticket_ids": unassigned or [],
        "solver_time_ms": round(solver_time_ms, 2),
        "scenario": None,
        "message": message,
        "ticket_results": [],
    }
