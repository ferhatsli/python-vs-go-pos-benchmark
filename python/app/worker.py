from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _open_alarm(
    session: AsyncSession,
    *,
    device_id: int,
    alarm_key: str,
    now: datetime,
) -> bool:
    existing = await session.scalar(
        text(
            """
            SELECT id FROM alarms
            WHERE device_id=:device_id AND alarm_key=:alarm_key AND status='OPEN'
            LIMIT 1
            """
        ),
        {"device_id": device_id, "alarm_key": alarm_key},
    )
    if existing is not None:
        return False
    await session.execute(
        text(
            """
            INSERT INTO alarms (device_id, alarm_key, status, opened_at)
            VALUES (:device_id, :alarm_key, 'OPEN', :opened_at)
            """
        ),
        {"device_id": device_id, "alarm_key": alarm_key, "opened_at": now},
    )
    return True


async def sweep_target_runtime(session: AsyncSession) -> dict[str, int]:
    now = datetime.now(UTC)

    activated = await session.execute(
        text(
            """
            UPDATE maintenance_windows
            SET status='ACTIVE'
            WHERE status='SCHEDULED' AND starts_at <= :now AND ends_at > :now
            """
        ),
        {"now": now},
    )
    completed = await session.execute(
        text(
            """
            UPDATE maintenance_windows
            SET status='COMPLETED'
            WHERE status IN ('SCHEDULED','ACTIVE') AND ends_at <= :now
            """
        ),
        {"now": now},
    )

    active_maintenance_ids = set(
        int(value)
        for value in (
            await session.scalars(
                text(
                    """
                    SELECT device_id FROM maintenance_windows
                    WHERE status='ACTIVE' AND starts_at <= :now AND ends_at > :now
                      AND device_id IS NOT NULL
                    """
                ),
                {"now": now},
            )
        ).all()
    )

    device_rows = (
        await session.execute(
            text(
                """
                SELECT d.id, d.station_id, cs.last_seen_at
                FROM devices d
                LEFT JOIN device_current_states cs ON cs.device_id=d.id
                WHERE d.status='ACTIVE'
                ORDER BY d.id
                """
            )
        )
    ).mappings().all()

    opened = 0
    resolved = 0
    for row in device_rows:
        device_id = int(row["id"])
        alarm_key = f"device:{device_id}:offline"
        # Intentionally one lookup per device: Track A preserves the frozen
        # worker's current algorithmic/N+1 query shape for language parity.
        existing = await session.scalar(
            text(
                """
                SELECT id FROM alarms
                WHERE device_id=:device_id AND alarm_key=:alarm_key AND status='OPEN'
                LIMIT 1
                """
            ),
            {"device_id": device_id, "alarm_key": alarm_key},
        )
        last_seen = row["last_seen_at"]
        is_offline = last_seen is not None and last_seen < now - timedelta(seconds=120)
        is_alarm_due = last_seen is not None and last_seen < now - timedelta(minutes=5)
        if is_alarm_due and device_id not in active_maintenance_ids:
            if existing is None:
                await session.execute(
                    text(
                        """
                        INSERT INTO alarms (device_id, alarm_key, status, opened_at)
                        VALUES (:device_id, :alarm_key, 'OPEN', :opened_at)
                        """
                    ),
                    {"device_id": device_id, "alarm_key": alarm_key, "opened_at": now},
                )
                opened += 1
        elif not is_offline and existing is not None:
            await session.execute(
                text(
                    """
                    UPDATE alarms SET status='RESOLVED', closed_at=:closed_at
                    WHERE id=:id AND status='OPEN'
                    """
                ),
                {"closed_at": now, "id": int(existing)},
            )
            resolved += 1

    failure_rows = (
        await session.execute(
            text(
                """
                SELECT device_id, count(*) AS failure_count
                FROM program_executions
                WHERE created_at >= :cutoff AND status IN ('FAILED','TIMEOUT')
                GROUP BY device_id
                HAVING count(*) >= 3
                """
            ),
            {"cutoff": now - timedelta(minutes=10)},
        )
    ).mappings().all()
    for row in failure_rows:
        created = await _open_alarm(
            session,
            device_id=int(row["device_id"]),
            alarm_key=f"device:{int(row['device_id'])}:execution-failures",
            now=now,
        )
        opened += int(created)

    await session.commit()
    return {
        "alarms_opened": opened,
        "alarms_resolved": resolved,
        "maintenance_activated": int(activated.rowcount or 0),  # type: ignore[attr-defined]
        "maintenance_completed": int(completed.rowcount or 0),  # type: ignore[attr-defined]
        "devices_evaluated": len(device_rows),
    }
