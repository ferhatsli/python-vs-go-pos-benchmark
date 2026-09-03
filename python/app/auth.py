from __future__ import annotations

from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.http import AppError


def device_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Device "):
        return ""
    return authorization.removeprefix("Device ").strip()


async def authenticate_device(session: AsyncSession, device_id: int, token: str) -> dict[str, object]:
    token_hash = sha256(token.encode("utf-8")).hexdigest()
    credential = await session.scalar(
        text(
            """
            SELECT id
            FROM device_credentials
            WHERE device_id = :device_id
              AND credential_hash = :token_hash
              AND status = 'ACTIVE'
            LIMIT 1
            """
        ),
        {"device_id": device_id, "token_hash": token_hash},
    )
    device = (
        await session.execute(
            text(
                """
                SELECT id, station_id, external_key, status
                FROM devices
                WHERE id = :device_id
                """
            ),
            {"device_id": device_id},
        )
    ).mappings().one_or_none()
    if credential is None or device is None or device["status"] != "ACTIVE":
        raise AppError(401, "INVALID_DEVICE_CREDENTIAL", "Cihaz kimliği doğrulanamadı.")
    return dict(device)
