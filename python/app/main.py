from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import authenticate_device, device_token
from app.commands import acknowledge_command, apply_command_result, pending_commands
from app.configuration import get_configuration
from app.dashboard import authenticate_panel, bearer_token, overview
from app.db import close_database, get_session
from app.heartbeat import record_heartbeat
from app.http import AppError, app_error_handler, success_response
from app.payments import create_payment
from app.settings import DEVICE_HEARTBEAT_SECONDS


class DeviceHeartbeatRequest(BaseModel):
    sequence: int | None = None
    app_version: str | None = Field(default=None, max_length=60)
    state: dict[str, object] = Field(default_factory=dict)


class DevicePaymentRequest(BaseModel):
    station_program_id: int | None = None
    payment_method: str
    configuration_version: int = Field(gt=0)
    displayed_price_minor: int | None = Field(default=None, gt=0)
    qr_token: str | None = None
    rf_uid: str | None = None
    test_scenario: str | None = None


class CommandResultRequest(BaseModel):
    result: str
    code: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=500)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_database()


app = FastAPI(lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True}


@app.post("/api/v1/device/heartbeat")
async def heartbeat(
    body: DeviceHeartbeatRequest,
    x_device_id: int = Header(alias="X-Device-Id"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    device = await authenticate_device(session, x_device_id, device_token(authorization))
    await record_heartbeat(
        session,
        device_id=int(device["id"]),
        sequence=body.sequence,
        app_version=body.app_version,
        state=body.state,
    )
    return success_response(
        {"accepted": True, "next_heartbeat_seconds": DEVICE_HEARTBEAT_SECONDS}
    )


@app.get("/api/v1/device/configuration")
async def configuration(
    current_version: int | None = Query(default=None, ge=1),
    x_device_id: int = Header(alias="X-Device-Id"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    device = await authenticate_device(session, x_device_id, device_token(authorization))
    data = await get_configuration(
        session,
        device_id=int(device["id"]),
        current_version=current_version,
    )
    return success_response(data)


@app.post("/api/v1/device/payments")
async def payment(
    body: DevicePaymentRequest,
    response: Response,
    x_idempotency_key: str = Header(alias="X-Idempotency-Key", min_length=8, max_length=128),
    x_device_id: int = Header(alias="X-Device-Id"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    device = await authenticate_device(session, x_device_id, device_token(authorization))
    payload = await create_payment(
        session,
        device=device,
        body=body.model_dump(mode="json"),
        idempotency_key=x_idempotency_key,
    )
    status = str(payload["status"])
    if status in {"FAILED", "CANCELLED"}:
        raise AppError(
            409,
            str(payload.get("error_code") or "PAYMENT_FAILED"),
            str(payload.get("error_code") or "Ödeme başarısız."),
            {"payment_id": payload["id"], "status": status},
        )
    if status == "PENDING":
        response.status_code = 202
    return success_response(payload)


@app.get("/api/v1/device/commands/pending")
async def commands_pending(
    limit: int = Query(default=20, ge=1, le=100),
    x_device_id: int = Header(alias="X-Device-Id"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    device = await authenticate_device(session, x_device_id, device_token(authorization))
    items = await pending_commands(session, int(device["id"]), limit)
    return success_response({"items": items, "next_poll_seconds": 5})


@app.post("/api/v1/device/commands/{command_id}/acknowledge")
async def command_acknowledge(
    command_id: int,
    x_device_id: int = Header(alias="X-Device-Id"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    device = await authenticate_device(session, x_device_id, device_token(authorization))
    payload = await acknowledge_command(session, int(device["id"]), command_id)
    return success_response(payload)


@app.post("/api/v1/device/commands/{command_id}/result")
async def command_result(
    command_id: int,
    body: CommandResultRequest,
    x_idempotency_key: str = Header(alias="X-Idempotency-Key", min_length=8, max_length=128),
    x_device_id: int = Header(alias="X-Device-Id"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    device = await authenticate_device(session, x_device_id, device_token(authorization))
    payload = await apply_command_result(
        session,
        device_id=int(device["id"]),
        command_id=command_id,
        result=body.result,
        code=body.code,
        message=body.message,
        idempotency_key=x_idempotency_key,
    )
    return success_response(payload)


@app.get("/api/v1/dashboard/overview")
async def dashboard_overview(
    period: str = Query(default="TODAY", pattern="^(TODAY|LAST_7_DAYS|THIS_MONTH)$"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    current = await authenticate_panel(session, bearer_token(authorization))
    return success_response(await overview(session, int(current["company_id"]), period))
