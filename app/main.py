from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.adapters import to_internal_payload
from app.lp_core import solve_lp
from app.schemas import RouteRequest, RouteResponse

SERVICE_NAME = "service-desk-route-api"
SERVICE_VERSION = "2.0.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(
    title="Service Desk Routing API",
    version=SERVICE_VERSION,
    description="Routes Service Desk tickets with an exact mixed-integer assignment model.",
)


def error_envelope(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "backend": "none",
        "objective_cost": 0.0,
        "processing_cost": 0.0,
        "penalty_cost": 0.0,
        "queue_penalty_cost": 0.0,
        "sla_penalty_cost": 0.0,
        "assignments": {},
        "unassigned_ticket_ids": [],
        "solver_time_ms": 0.0,
        "scenario": None,
        "message": message,
        "ticket_results": [],
    }


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in exc.errors()
    )
    logger.warning("validation_error path=%s details=%s", request.url.path, details)
    return JSONResponse(status_code=422, content=error_envelope(details))


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error path=%s", request.url.path)
    return JSONResponse(status_code=500, content=error_envelope("internal server error"))


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request method=%s path=%s status=%s elapsed_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.post("/route", response_model=RouteResponse)
def route(payload: RouteRequest) -> RouteResponse:
    internal = to_internal_payload(payload)
    result = solve_lp(internal)
    return RouteResponse.model_validate(result)
