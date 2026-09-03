from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record_heartbeat(
    session: AsyncSession,
    *,
    device_id: int,
    sequence: int | None,
    app_version: str | None,
    state: dict[str, object],
) -> None:
    now = datetime.now(UTC)
    payload = json.dumps(state, separators=(",", ":"), sort_keys=True)

    await session.execute(
        text(
            """
            INSERT INTO device_heartbeats (
                device_id, occurred_at, received_at, sequence, payload
            ) VALUES (
                :device_id, :now, :now, :sequence, CAST(:payload AS JSONB)
            )
            """
        ),
        {
            "device_id": device_id,
            "now": now,
            "sequence": sequence,
            "payload": payload,
        },
    )

    current = await session.scalar(
        text("SELECT device_id FROM device_current_states WHERE device_id = :device_id"),
        {"device_id": device_id},
    )
    if current is None:
        await session.execute(
            text(
                """
                INSERT INTO device_current_states (
                    device_id, state_payload, updated_at
                ) VALUES (
                    :device_id, '{}'::jsonb, :now
                )
                """
            ),
            {"device_id": device_id, "now": now},
        )

    await session.execute(
        text(
            """
            UPDATE device_current_states
            SET last_seen_at = :now,
                app_version = :app_version,
                state_payload = CAST(:payload AS JSONB),
                updated_at = :now
            WHERE device_id = :device_id
            """
        ),
        {
            "device_id": device_id,
            "now": now,
            "app_version": app_version,
            "payload": payload,
        },
    )
    await session.commit()
