from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import get_session_factory
from app.worker import sweep_target_runtime

DATABASE_URL = os.environ.get(
    "BENCH_DATABASE_URL",
    "postgresql+asyncpg://benchmark:benchmark-local-only@postgres:5432/pos_benchmark",
)


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


async def run_sweep() -> dict[str, int]:
    async with get_session_factory()() as session:
        return await sweep_target_runtime(session)


@pytest.mark.asyncio(loop_scope="session")
async def test_worker_dedupes_and_resolves_offline_alarm_while_preserving_n_plus_one_shape() -> None:
    await execute(
        """
        UPDATE device_current_states SET last_seen_at=now(), updated_at=now();
        UPDATE device_current_states SET last_seen_at=now()-interval '10 minutes' WHERE device_id=1;
        DELETE FROM maintenance_windows WHERE device_id=1;
        DELETE FROM alarms WHERE alarm_key LIKE 'device%offline';
        SELECT pg_stat_statements_reset();
        """
    )

    first = await run_sweep()
    assert first["alarms_opened"] == 1
    assert int(
        await scalar(
            "SELECT count(*) FROM alarms WHERE device_id=1 AND alarm_key='device:1:offline' AND status='OPEN'"
        )
    ) == 1

    calls = int(
        await scalar(
            """
            SELECT coalesce(sum(calls),0) FROM pg_stat_statements
            WHERE query LIKE '%FROM alarms%' AND query LIKE '%alarm_key%'
              AND query LIKE '%device_id%'
            """
        )
    )
    assert calls >= 500

    second = await run_sweep()
    assert second["alarms_opened"] == 0
    assert int(
        await scalar(
            "SELECT count(*) FROM alarms WHERE device_id=1 AND alarm_key='device:1:offline' AND status='OPEN'"
        )
    ) == 1

    await execute("UPDATE device_current_states SET last_seen_at=now(), updated_at=now() WHERE device_id=1")
    recovered = await run_sweep()
    assert recovered["alarms_resolved"] == 1
    assert await scalar(
        "SELECT status FROM alarms WHERE device_id=1 AND alarm_key='device:1:offline' ORDER BY id DESC LIMIT 1"
    ) == "RESOLVED"


@pytest.mark.asyncio(loop_scope="session")
async def test_worker_updates_maintenance_windows_and_dedupes_repeated_failure_alarm() -> None:
    await execute(
        """
        DELETE FROM maintenance_windows WHERE device_id=1;
        DELETE FROM alarms WHERE alarm_key='device:1:execution-failures';
        INSERT INTO maintenance_windows (device_id, starts_at, ends_at, status)
        VALUES (1, now()-interval '1 minute', now()+interval '1 minute', 'SCHEDULED');
        INSERT INTO maintenance_windows (device_id, starts_at, ends_at, status)
        VALUES (1, now()-interval '10 minutes', now()-interval '5 minutes', 'ACTIVE');
        UPDATE program_executions
        SET device_id=1, status='FAILED', created_at=now()-interval '2 minutes', completed_at=now()-interval '1 minute'
        WHERE id IN (1,2,3);
        """
    )

    first = await run_sweep()
    second = await run_sweep()

    assert first["maintenance_activated"] == 1
    assert first["maintenance_completed"] == 1
    assert int(
        await scalar(
            "SELECT count(*) FROM alarms WHERE alarm_key='device:1:execution-failures' AND status='OPEN'"
        )
    ) == 1
    assert second["alarms_opened"] == 0
