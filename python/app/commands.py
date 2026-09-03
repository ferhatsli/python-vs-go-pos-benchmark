from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.http import AppError
from app.settings import CSRF_SECRET


def _result_hash(result: str, code: str | None, message: str | None) -> str:
    raw = f"{result}:{code}:{message}"
    return hmac.new(CSRF_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()


async def _mapping(session: AsyncSession, sql: str, **params: object) -> dict[str, object] | None:
    result = await session.execute(text(sql), params)
    row = result.mappings().first()
    return dict(row) if row is not None else None


async def pending_commands(session: AsyncSession, device_id: int, limit: int) -> list[dict[str, object]]:
    result = await session.execute(
        text(
            """
            SELECT id, program_execution_id, command_key, status, payload,
                   created_at, sent_at, acknowledged_at
            FROM commands
            WHERE device_id=:device_id AND status IN ('PENDING','SENT')
            ORDER BY created_at, id
            LIMIT :limit
            """
        ),
        {"device_id": device_id, "limit": limit},
    )
    rows = [dict(row) for row in result.mappings().all()]
    now = datetime.now(UTC)
    for row in rows:
        if row["status"] == "PENDING":
            await session.execute(
                text("UPDATE commands SET status='SENT', sent_at=:now WHERE id=:id"),
                {"now": now, "id": int(row["id"])},
            )
            await session.execute(
                text(
                    """
                    UPDATE program_executions SET status='COMMAND_SENT'
                    WHERE id=:execution_id AND status='CREATED'
                    """
                ),
                {"execution_id": int(row["program_execution_id"])},
            )
            row["status"] = "SENT"
            row["sent_at"] = now
    await session.commit()
    return [
        {
            "id": str(row["id"]),
            "execution_id": str(row["program_execution_id"]),
            "type": "EXECUTE_PROGRAM",
            "status": row["status"],
            "payload": row["payload"],
            "created_at": row["created_at"].isoformat(),
            "sent_at": row["sent_at"].isoformat() if row["sent_at"] else None,
            "ack_deadline_at": (row["created_at"] + timedelta(seconds=30)).isoformat(),
            "result_deadline_at": (
                (row["acknowledged_at"] + timedelta(seconds=120)).isoformat()
                if row["acknowledged_at"]
                else None
            ),
        }
        for row in rows
    ]


async def acknowledge_command(session: AsyncSession, device_id: int, command_id: int) -> dict[str, object]:
    command = await _mapping(
        session,
        """
        SELECT id, program_execution_id, status, created_at, acknowledged_at, result_code
        FROM commands
        WHERE id=:command_id AND device_id=:device_id
        FOR UPDATE
        """,
        command_id=command_id,
        device_id=device_id,
    )
    if command is None:
        raise AppError(404, "COMMAND_NOT_FOUND", "Komut bulunamadı.")
    now = datetime.now(UTC)
    if command["status"] in {"PENDING", "SENT"} and command["created_at"] <= now - timedelta(seconds=30):
        raise AppError(409, "COMMAND_EXPIRED", "Komut onay süresi doldu.")
    if command["status"] in {"PENDING", "SENT"}:
        await session.execute(
            text("UPDATE commands SET status='ACKNOWLEDGED', acknowledged_at=:now WHERE id=:id"),
            {"now": now, "id": command_id},
        )
        await session.execute(
            text(
                """
                UPDATE program_executions
                SET status='RUNNING', started_at=:now
                WHERE id=:execution_id
                """
            ),
            {"now": now, "execution_id": int(command["program_execution_id"])},
        )
        command["status"] = "ACKNOWLEDGED"
        command["acknowledged_at"] = now
        await session.commit()
    elif command["status"] not in {"ACKNOWLEDGED", "SUCCESS", "FAILED"}:
        raise AppError(409, "COMMAND_NOT_ACKNOWLEDGEABLE", "Komut onaylanamaz.")
    return {"id": str(command["id"]), "status": command["status"]}


async def apply_command_result(
    session: AsyncSession,
    *,
    device_id: int,
    command_id: int,
    result: str,
    code: str | None,
    message: str | None,
    idempotency_key: str,
) -> dict[str, object]:
    if result not in {"SUCCESS", "FAILED"}:
        raise AppError(422, "INVALID_COMMAND_RESULT", "Komut sonucu geçersiz.")
    command = await _mapping(
        session,
        """
        SELECT id, program_execution_id, status, acknowledged_at, result_code
        FROM commands
        WHERE id=:command_id AND device_id=:device_id
        FOR UPDATE
        """,
        command_id=command_id,
        device_id=device_id,
    )
    if command is None:
        raise AppError(404, "COMMAND_NOT_FOUND", "Komut bulunamadı.")

    request_hash = _result_hash(result, code, message)
    existing = await _mapping(
        session,
        """
        SELECT result_key, request_hash, status, code
        FROM command_results WHERE command_id=:command_id
        """,
        command_id=command_id,
    )
    if existing is not None:
        if existing["result_key"] != idempotency_key or existing["request_hash"] != request_hash:
            raise AppError(409, "IDEMPOTENCY_CONFLICT", "Komut sonucu daha önce farklı işlendi.")
        return {
            "id": str(command["id"]),
            "status": existing["status"],
            "result_code": existing["code"],
        }

    if command["status"] != "ACKNOWLEDGED":
        raise AppError(409, "COMMAND_NOT_RUNNING", "Komut çalışır durumda değil.")
    now = datetime.now(UTC)
    if command["acknowledged_at"] and command["acknowledged_at"] <= now - timedelta(seconds=120):
        raise AppError(409, "COMMAND_RESULT_EXPIRED", "Komut sonuç süresi doldu.")

    await session.execute(
        text(
            """
            INSERT INTO command_results (
                command_id, result_key, request_hash, status, code, message, payload, created_at
            ) VALUES (
                :command_id, :result_key, :request_hash, :status, :code, :message,
                CAST(:payload AS jsonb), :created_at
            )
            """
        ),
        {
            "command_id": command_id,
            "result_key": idempotency_key,
            "request_hash": request_hash,
            "status": result,
            "code": code,
            "message": message,
            "payload": json.dumps({"result": result, "code": code, "message": message}),
            "created_at": now,
        },
    )
    await session.execute(
        text(
            """
            UPDATE commands
            SET status=:status, completed_at=:now, result_code=:code
            WHERE id=:command_id
            """
        ),
        {"status": result, "now": now, "code": code, "command_id": command_id},
    )
    await session.execute(
        text(
            """
            UPDATE program_executions
            SET status=:status, completed_at=:now
            WHERE id=:execution_id
            """
        ),
        {"status": result, "now": now, "execution_id": int(command["program_execution_id"])},
    )
    await session.execute(
        text(
            """
            INSERT INTO events (device_id, event_type, payload, created_at)
            VALUES (:device_id, 'execution.completed', CAST(:payload AS jsonb), :created_at)
            """
        ),
        {
            "device_id": device_id,
            "payload": json.dumps({"command_id": command_id, "status": result, "code": code}),
            "created_at": now,
        },
    )
    await session.commit()
    return {"id": str(command_id), "status": result, "result_code": code}
