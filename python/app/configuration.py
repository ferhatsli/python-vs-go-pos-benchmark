from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.http import AppError


async def get_configuration(
    session: AsyncSession,
    *,
    device_id: int,
    current_version: int | None,
) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT id, version, checksum, snapshot
                FROM device_configurations
                WHERE device_id = :device_id
                  AND status = 'PUBLISHED'
                """
            ),
            {"device_id": device_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AppError(404, "CONFIGURATION_NOT_FOUND", "Cihaz yapılandırması bulunamadı.")
    snapshot = dict(row["snapshot"] or {})
    return {
        "id": str(row["id"]),
        "version": int(row["version"]),
        "checksum": str(row["checksum"]),
        "update_available": current_version != int(row["version"]),
        **snapshot,
    }
