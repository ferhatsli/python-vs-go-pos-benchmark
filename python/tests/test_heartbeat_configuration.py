from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import app

DATABASE_URL = os.environ.get(
    "BENCH_DATABASE_URL",
    "postgresql+asyncpg://benchmark:benchmark-local-only@postgres:5432/pos_benchmark",
)


def device_headers(device_id: int = 1, token: str | None = None) -> dict[str, str]:
    return {
        "X-Device-Id": str(device_id),
        "Authorization": f"Device {token or f'credential-{device_id}'}",
    }


async def scalar(sql: str, **params: object) -> object:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(text(sql), params)
    finally:
        await engine.dispose()


@pytest.mark.asyncio(loop_scope="session")
async def test_heartbeat_rejects_invalid_device_credential() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/device/heartbeat",
            headers=device_headers(token="wrong-token"),
            json={"sequence": 42, "app_version": "1.2.3", "state": {"health": "OK"}},
        )

    assert response.status_code == 401
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_DEVICE_CREDENTIAL"


@pytest.mark.asyncio(loop_scope="session")
async def test_heartbeat_persists_raw_row_and_updates_current_state() -> None:
    before = int(await scalar("SELECT count(*) FROM device_heartbeats WHERE device_id=:id", id=1))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/device/heartbeat",
            headers=device_headers(),
            json={
                "sequence": 4242,
                "app_version": "9.9.9",
                "state": {"health": "OK", "signal": 88},
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"] == {"accepted": True, "next_heartbeat_seconds": 30}
    assert int(await scalar("SELECT count(*) FROM device_heartbeats WHERE device_id=:id", id=1)) == before + 1
    assert await scalar("SELECT app_version FROM device_current_states WHERE device_id=:id", id=1) == "9.9.9"
    assert await scalar(
        "SELECT state_payload->>'signal' FROM device_current_states WHERE device_id=:id", id=1
    ) == "88"


@pytest.mark.asyncio(loop_scope="session")
async def test_configuration_is_device_scoped_and_preserves_frozen_snapshot() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        current = await client.get(
            "/api/v1/device/configuration?current_version=1", headers=device_headers()
        )
        unknown = await client.get("/api/v1/device/configuration", headers=device_headers())

    assert current.status_code == 200, current.text
    data = current.json()["data"]
    assert data["version"] == 1
    assert len(data["checksum"]) == 32
    assert data["update_available"] is False
    assert data["device_id"] == "dev-0000001"
    assert data["station_id"] == "stn-000001"
    assert data["heartbeat_seconds"] == 30
    assert data["currency"] == "TRY"
    assert unknown.status_code == 200
    assert unknown.json()["data"]["update_available"] is True
