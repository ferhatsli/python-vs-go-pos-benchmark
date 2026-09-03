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


def headers(key: str | None = None) -> dict[str, str]:
    value = {
        "X-Device-Id": "1",
        "Authorization": "Device credential-1",
    }
    if key is not None:
        value["X-Idempotency-Key"] = key
    return value


async def execute(sql: str) -> None:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            for statement in (part.strip() for part in sql.split(";")):
                if statement:
                    await conn.execute(text(statement))
    finally:
        await engine.dispose()


async def scalar(sql: str) -> object:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(text(sql))
    finally:
        await engine.dispose()


async def prepare_command(command_id: int) -> None:
    await execute(
        f"""
        DELETE FROM command_results WHERE command_id={command_id};
        UPDATE commands
        SET device_id=1, status='PENDING', sent_at=NULL, acknowledged_at=NULL, completed_at=NULL,
            result_code=NULL, created_at=now()
        WHERE id={command_id};
        UPDATE program_executions
        SET device_id=1, wash_bay_id=1, status='CREATED', started_at=NULL, completed_at=NULL
        WHERE id=(SELECT program_execution_id FROM commands WHERE id={command_id});
        """
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_command_lifecycle_and_result_idempotency() -> None:
    await prepare_command(1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pending = await client.get("/api/v1/device/commands/pending", headers=headers())
        assert pending.status_code == 200, pending.text
        item = next(item for item in pending.json()["data"]["items"] if item["id"] == "1")
        assert item["status"] == "SENT"
        assert await scalar("SELECT status FROM program_executions WHERE id=1") == "COMMAND_SENT"

        ack = await client.post("/api/v1/device/commands/1/acknowledge", headers=headers())
        assert ack.status_code == 200, ack.text
        assert ack.json()["data"]["status"] == "ACKNOWLEDGED"
        assert await scalar("SELECT status FROM program_executions WHERE id=1") == "RUNNING"

        result = await client.post(
            "/api/v1/device/commands/1/result",
            headers=headers("bench-command-result"),
            json={"result": "SUCCESS", "code": None, "message": None},
        )
        duplicate = await client.post(
            "/api/v1/device/commands/1/result",
            headers=headers("bench-command-result"),
            json={"result": "SUCCESS", "code": None, "message": None},
        )
        conflict = await client.post(
            "/api/v1/device/commands/1/result",
            headers=headers("bench-command-result"),
            json={"result": "FAILED", "code": "HW", "message": "different"},
        )

    assert result.status_code == 200, result.text
    assert result.json()["data"]["status"] == "SUCCESS"
    assert duplicate.status_code == 200
    assert duplicate.json()["data"]["status"] == "SUCCESS"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert await scalar("SELECT status FROM program_executions WHERE id=1") == "SUCCESS"
    assert int(await scalar("SELECT count(*) FROM command_results WHERE command_id=1")) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_command_cannot_complete_before_acknowledge() -> None:
    await prepare_command(2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pending = await client.get("/api/v1/device/commands/pending", headers=headers())
        assert pending.status_code == 200
        response = await client.post(
            "/api/v1/device/commands/2/result",
            headers=headers("bench-command-early"),
            json={"result": "SUCCESS", "code": None, "message": None},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COMMAND_NOT_RUNNING"
    assert int(await scalar("SELECT count(*) FROM command_results WHERE command_id=2")) == 0
