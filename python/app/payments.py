from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.http import AppError
from app.settings import CSRF_SECRET, QR_PEPPER


def secret_hash(value: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), value.encode(), hashlib.sha256).hexdigest()


def normalize_uid(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Fa-f]", "", value).upper()
    if len(normalized) < 8 or len(normalized) > 64 or len(normalized) % 2:
        raise AppError(422, "INVALID_RF_UID", "RF UID biçimi geçersiz.")
    return normalized


def request_hash(body: dict[str, object]) -> str:
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return secret_hash(encoded, CSRF_SECRET)


async def _mapping(session: AsyncSession, sql: str, **params: object) -> dict[str, object] | None:
    result = await session.execute(text(sql), params)
    row = result.mappings().first()
    return dict(row) if row is not None else None


async def _scalar(session: AsyncSession, sql: str, **params: object) -> object:
    return await session.scalar(text(sql), params)


async def payment_payload(session: AsyncSession, payment_id: int) -> dict[str, object]:
    payment = await _mapping(
        session,
        """
        SELECT id, status, method, amount_minor, currency, error_code, created_at, program_id
        FROM payment_transactions WHERE id=:id
        """,
        id=payment_id,
    )
    if payment is None:
        raise AppError(404, "PAYMENT_NOT_FOUND", "Ödeme bulunamadı.")
    right = await _mapping(
        session,
        "SELECT id, status FROM start_rights WHERE payment_id=:id",
        id=payment_id,
    )
    execution = await _mapping(
        session,
        "SELECT id, status FROM program_executions WHERE payment_id=:id",
        id=payment_id,
    )
    return {
        "id": str(payment["id"]),
        "code": f"PAY-{int(payment['id']):012d}",
        "status": payment["status"],
        "payment_method": payment["method"],
        "amount_minor": int(payment["amount_minor"]),
        "currency": payment["currency"],
        "error_code": payment["error_code"],
        "station_program_id": str(payment["program_id"]) if payment["program_id"] is not None else None,
        "created_at": payment["created_at"].isoformat(),
        "start_right": (
            {"id": str(right["id"]), "status": right["status"]} if right is not None else None
        ),
        "execution": (
            {"id": str(execution["id"]), "status": execution["status"]}
            if execution is not None
            else None
        ),
    }


async def create_payment(
    session: AsyncSession,
    *,
    device: dict[str, object],
    body: dict[str, object],
    idempotency_key: str,
) -> dict[str, object]:
    device_id = int(device["id"])
    station_id = int(device["station_id"])
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"payment:{device_id}:{idempotency_key}"},
    )

    body_hash = request_hash(body)
    existing = await _mapping(
        session,
        """
        SELECT id, request_hash FROM payment_transactions
        WHERE device_id=:device_id AND idempotency_key=:key
        """,
        device_id=device_id,
        key=idempotency_key,
    )
    if existing is not None:
        if existing["request_hash"] != body_hash:
            raise AppError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "Aynı anahtar farklı bir ödeme isteğinde kullanıldı.",
            )
        return await payment_payload(session, int(existing["id"]))

    now = datetime.now(UTC)
    if device["status"] != "ACTIVE":
        raise AppError(409, "DEVICE_NOT_OPERATIONAL", "Cihaz işlem için aktif değil.")

    station = await _mapping(
        session,
        "SELECT company_id FROM stations WHERE id=:station_id",
        station_id=station_id,
    )
    if station is None:
        raise AppError(409, "DEVICE_NOT_OPERATIONAL", "Cihaz istasyonu bulunamadı.")
    company_id = int(station["company_id"])

    state = await _mapping(
        session,
        """
        SELECT last_seen_at, acknowledged_configuration_version
        FROM device_current_states WHERE device_id=:device_id
        """,
        device_id=device_id,
    )
    if state is None or state["last_seen_at"] is None or state["last_seen_at"] < now - timedelta(seconds=120):
        raise AppError(409, "DEVICE_OFFLINE", "Çevrimdışı cihazda ödeme başlatılamaz.")

    wash_bay = await _mapping(
        session,
        "SELECT id, status FROM wash_bays WHERE device_id=:device_id",
        device_id=device_id,
    )
    if wash_bay is None:
        raise AppError(409, "DEVICE_NOT_ASSIGNED", "Cihaz bir perona bağlı değil.")
    wash_bay_id = int(wash_bay["id"])

    maintenance = await _scalar(
        session,
        """
        SELECT id FROM maintenance_windows
        WHERE device_id=:device_id AND status='ACTIVE' AND starts_at <= :now AND ends_at > :now
        LIMIT 1
        """,
        device_id=device_id,
        now=now,
    )
    if maintenance is not None:
        raise AppError(409, "DEVICE_IN_MAINTENANCE", "Bakım durumundaki cihazda ödeme başlatılamaz.")

    configuration = await _mapping(
        session,
        """
        SELECT version FROM device_configurations
        WHERE device_id=:device_id AND status='PUBLISHED'
        """,
        device_id=device_id,
    )
    requested_version = int(body["configuration_version"])
    if (
        configuration is None
        or int(configuration["version"]) != requested_version
        or state["acknowledged_configuration_version"] != int(configuration["version"])
    ):
        raise AppError(
            409,
            "CONFIGURATION_NOT_ACKNOWLEDGED",
            "Güncel cihaz yapılandırması uygulanmadan ödeme başlatılamaz.",
        )

    busy = await _scalar(
        session,
        """
        SELECT id FROM program_executions
        WHERE wash_bay_id=:wash_bay_id AND status IN ('CREATED','COMMAND_SENT','RUNNING')
        LIMIT 1
        """,
        wash_bay_id=wash_bay_id,
    )
    if busy is not None:
        raise AppError(409, "WASH_BAY_BUSY", "Peronda devam eden bir program bulunuyor.")

    method = str(body["payment_method"])
    qr_preflight: dict[str, object] | None = None
    if method == "QR":
        token_hash = secret_hash(str(body.get("qr_token") or ""), QR_PEPPER)
        qr_preflight = await _mapping(
            session,
            """
            SELECT id, company_id, station_id, program_id
            FROM qr_codes WHERE token_hash=:token_hash
            """,
            token_hash=token_hash,
        )
        if (
            qr_preflight is None
            or int(qr_preflight["company_id"]) != company_id
            or int(qr_preflight["station_id"]) != station_id
        ):
            raise AppError(404, "QR_NOT_FOUND", "QR kod bu istasyonda geçerli değil.")
        program_id = int(qr_preflight["program_id"])
    else:
        if body.get("station_program_id") is None:
            raise AppError(422, "STATION_PROGRAM_REQUIRED", "Program zorunludur.")
        program_id = int(body["station_program_id"])

    program = await _mapping(
        session,
        """
        SELECT id, price_minor FROM programs
        WHERE id=:program_id AND company_id=:company_id AND active=TRUE
        """,
        program_id=program_id,
        company_id=company_id,
    )
    if program is None:
        raise AppError(409, "PROGRAM_NOT_AVAILABLE", "Program kullanılamıyor.")

    entitlement = await _scalar(
        session,
        """
        SELECT id FROM entitlements
        WHERE device_id=:device_id AND program_id=:program_id AND enabled=TRUE
        """,
        device_id=device_id,
        program_id=program_id,
    )
    if entitlement is None:
        raise AppError(409, "ENTITLEMENT_REQUIRED", "Cihaz program yetkisine sahip değil.")

    method_enabled = await _scalar(
        session,
        """
        SELECT id FROM program_payment_methods
        WHERE program_id=:program_id AND payment_method=:method AND enabled=TRUE
        """,
        program_id=program_id,
        method=method,
    )
    if method_enabled is None:
        raise AppError(409, "PAYMENT_METHOD_NOT_AVAILABLE", "Ödeme yöntemi bu programda açık değil.")

    program_price = int(program["price_minor"])
    if method in {"CARD", "RF_CARD"} and int(body.get("displayed_price_minor") or 0) != program_price:
        raise AppError(
            409,
            "PROGRAM_PRICE_CHANGED",
            "Program fiyatı değişti. Güncel fiyatı onaylayıp tekrar deneyin.",
            {"current_price_minor": program_price},
        )

    status = "SUCCESS"
    error_code: str | None = None
    error_message: str | None = None
    amount_minor = program_price
    qr_code_id: int | None = None
    rf_wallet_id: int | None = None

    if method == "CARD":
        mapping = {
            "TEST_SUCCESS": ("SUCCESS", None),
            "TEST_FAILED": ("FAILED", "CARD_DECLINED"),
            "TEST_CANCELLED": ("CANCELLED", "CARD_CANCELLED"),
            "TEST_TIMEOUT": ("PENDING", None),
            "TEST_INSUFFICIENT_FUNDS": ("FAILED", "INSUFFICIENT_FUNDS"),
            "TEST_PROVIDER_ERROR": ("FAILED", "PROVIDER_ERROR"),
        }
        scenario = str(body.get("test_scenario") or "")
        if scenario not in mapping:
            raise AppError(422, "INVALID_TEST_SCENARIO", "Kart test senaryosu geçersiz.")
        status, error_code = mapping[scenario]
        error_message = error_code

    elif method == "QR":
        token_hash = secret_hash(str(body.get("qr_token") or ""), QR_PEPPER)
        qr = await _mapping(
            session,
            """
            SELECT id, company_id, station_id, program_id, amount_minor, currency,
                   usage_limit, usage_count, status, starts_at, expires_at
            FROM qr_codes WHERE token_hash=:token_hash
            FOR UPDATE
            """,
            token_hash=token_hash,
        )
        if (
            qr is None
            or qr["status"] != "ACTIVE"
            or int(qr["company_id"]) != company_id
            or int(qr["station_id"]) != station_id
            or int(qr["program_id"]) != program_id
            or qr["starts_at"] > now
            or qr["expires_at"] <= now
            or int(qr["usage_count"]) >= int(qr["usage_limit"])
        ):
            status, error_code, error_message = "FAILED", "QR_INVALID", "QR_INVALID"
        else:
            qr_code_id = int(qr["id"])
            amount_minor = int(qr["amount_minor"])
            new_usage = int(qr["usage_count"]) + 1
            new_status = "USED" if new_usage >= int(qr["usage_limit"]) else "ACTIVE"
            await session.execute(
                text("UPDATE qr_codes SET usage_count=:usage, status=:status WHERE id=:id"),
                {"usage": new_usage, "status": new_status, "id": qr_code_id},
            )

    elif method == "RF_CARD":
        uid = normalize_uid(str(body.get("rf_uid") or ""))
        uid_hash = secret_hash(uid, QR_PEPPER)
        card = await _mapping(
            session,
            """
            SELECT id, company_id, status, expires_at FROM rf_cards WHERE uid_hash=:uid_hash
            """,
            uid_hash=uid_hash,
        )
        if (
            card is None
            or card["status"] != "ACTIVE"
            or int(card["company_id"]) != company_id
            or (card["expires_at"] is not None and card["expires_at"] <= now)
        ):
            status, error_code, error_message = "FAILED", "RF_CARD_INVALID", "RF_CARD_INVALID"
        else:
            wallet = await _mapping(
                session,
                """
                SELECT id, balance_minor, version FROM rf_wallets
                WHERE rf_card_id=:rf_card_id FOR UPDATE
                """,
                rf_card_id=int(card["id"]),
            )
            if wallet is None or int(wallet["balance_minor"]) < program_price:
                status, error_code, error_message = (
                    "FAILED",
                    "RF_INSUFFICIENT_BALANCE",
                    "RF_INSUFFICIENT_BALANCE",
                )
            else:
                rf_wallet_id = int(wallet["id"])
                await session.execute(
                    text(
                        """
                        UPDATE rf_wallets
                        SET balance_minor=balance_minor-:amount, version=version+1, updated_at=:now
                        WHERE id=:id
                        """
                    ),
                    {"amount": program_price, "now": now, "id": rf_wallet_id},
                )
    else:
        raise AppError(422, "UNSUPPORTED_PAYMENT_METHOD", "Ödeme yöntemi desteklenmiyor.")

    payment_id = int(
        await session.scalar(
            text(
                """
                INSERT INTO payment_transactions (
                    device_id, station_id, idempotency_key, request_hash, method,
                    amount_minor, currency, status, error_code, error_message,
                    program_id, qr_code_id, rf_wallet_id, created_at, completed_at
                ) VALUES (
                    :device_id, :station_id, :key, :request_hash, :method,
                    :amount_minor, 'TRY', :status, :error_code, :error_message,
                    :program_id, :qr_code_id, :rf_wallet_id, :created_at, :completed_at
                ) RETURNING id
                """
            ),
            {
                "device_id": device_id,
                "station_id": station_id,
                "key": idempotency_key,
                "request_hash": body_hash,
                "method": method,
                "amount_minor": amount_minor,
                "status": status,
                "error_code": error_code,
                "error_message": error_message,
                "program_id": program_id,
                "qr_code_id": qr_code_id,
                "rf_wallet_id": rf_wallet_id,
                "created_at": now,
                "completed_at": None if status == "PENDING" else now,
            },
        )
    )

    await session.execute(
        text(
            """
            INSERT INTO payment_attempts (payment_id, attempt_no, status, created_at)
            VALUES (:payment_id, 1, :status, :created_at)
            """
        ),
        {"payment_id": payment_id, "status": status, "created_at": now},
    )

    if method == "CARD":
        await session.execute(
            text(
                """
                INSERT INTO provider_transactions (payment_id, provider_ref, status, created_at)
                VALUES (:payment_id, :provider_ref, :status, :created_at)
                """
            ),
            {
                "payment_id": payment_id,
                "provider_ref": f"MOCK-{payment_id}",
                "status": status,
                "created_at": now,
            },
        )

    if method == "RF_CARD" and status == "SUCCESS" and rf_wallet_id is not None:
        await session.execute(
            text(
                """
                INSERT INTO rf_wallet_ledger (
                    wallet_id, payment_id, direction, amount_minor, created_at
                ) VALUES (:wallet_id, :payment_id, 'DEBIT', :amount_minor, :created_at)
                """
            ),
            {
                "wallet_id": rf_wallet_id,
                "payment_id": payment_id,
                "amount_minor": program_price,
                "created_at": now,
            },
        )

    if status == "SUCCESS":
        await session.execute(
            text(
                """
                INSERT INTO start_rights (
                    payment_id, device_id, wash_bay_id, program_id, status, created_at
                ) VALUES (:payment_id, :device_id, :wash_bay_id, :program_id, 'AVAILABLE', :created_at)
                """
            ),
            {
                "payment_id": payment_id,
                "device_id": device_id,
                "wash_bay_id": wash_bay_id,
                "program_id": program_id,
                "created_at": now,
            },
        )

    await session.execute(
        text(
            """
            INSERT INTO events (device_id, payment_id, event_type, payload, created_at)
            VALUES (:device_id, :payment_id, 'payment.completed', CAST(:payload AS jsonb), :created_at)
            """
        ),
        {
            "device_id": device_id,
            "payment_id": payment_id,
            "payload": json.dumps({"status": status, "method": method, "error_code": error_code}),
            "created_at": now,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO audit_entries (payment_id, action, payload, created_at)
            VALUES (:payment_id, 'payment.completed', CAST(:payload AS jsonb), :created_at)
            """
        ),
        {
            "payment_id": payment_id,
            "payload": json.dumps({"status": status}),
            "created_at": now,
        },
    )

    await session.commit()
    return await payment_payload(session, payment_id)
