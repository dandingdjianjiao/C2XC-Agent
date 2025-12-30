from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


@dataclass
class APIError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] | None = None


def error_response(*, status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return JSONResponse(status_code=int(status_code), content=payload)


async def api_error_handler(_req: Request, exc: APIError) -> JSONResponse:
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def validation_error_handler(_req: Request, exc: RequestValidationError) -> JSONResponse:
    # Normalize Pydantic validation errors into our contract envelope.
    return error_response(
        status_code=400,
        code="invalid_argument",
        message="Request validation failed.",
        details={"errors": exc.errors()},
    )


async def unhandled_error_handler(_req: Request, exc: Exception) -> JSONResponse:
    # Keep errors safe by default; details are still traceable via server logs / sqlite events.
    return error_response(
        status_code=500,
        code="internal",
        message="Internal server error.",
        details={"type": type(exc).__name__},
    )
