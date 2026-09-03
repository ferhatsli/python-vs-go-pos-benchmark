from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: object | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def meta() -> dict[str, str]:
    return {
        "request_id": uuid4().hex,
        "server_time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def success_response(data: object) -> dict[str, object]:
    return {"success": True, "data": data, "meta": meta()}


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            "meta": meta(),
        },
    )
