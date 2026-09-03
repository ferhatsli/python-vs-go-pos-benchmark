from __future__ import annotations

import asyncio
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


def device_headers(key: str, device_id: int = 1) -> dict[str, str]:
    return {
        "X-Device-Id": str(device_id),
        "Authorization": f"Device credential-{device_id}",
        "X-Idempotency-Key": key,
    }


async def execute(sql: str, **params: object) -> None:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            for statement in (part.strip() for part in sql.split(";")):
                if statement:
                    await conn.execute(text(statement), params)
    finally:
        await engine.dispose()


async def scalar(sql: str, **params: object) -> object:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(text(sql), params)
    finally:
        await engine.dispose()


async def prepare_device() -> None:
    await execute(
        """
        UPDATE device_current_states
        SET last_seen_at=now(), current_configuration_version=1,
            acknowledged_configuration_version=1, updated_at=now()
        WHERE device_id=1;
        UPDATE devices SET status='ACTIVE' WHERE id=1;
        UPDATE wash_bays SET status='IDLE' WHERE device_id=1;
        UPDATE program_executions SET status='SUCCESS', completed_at=now() WHERE device_id=1;
        DELETE FROM maintenance_windows WHERE device_id=1;
        UPDATE entitlements SET enabled=TRUE WHERE device_id=1 AND program_id=1;
        UPDATE program_payment_methods SET enabled=TRUE WHERE program_id=1;
        """
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_card_payment_is_idempotent_and_conflicting_reuse_is_rejected() -> None:
    await prepare_device()
    await execute("DELETE FROM payment_transactions WHERE idempotency_key LIKE 'bench-card-%'")
    body = {
        "station_program_id": 1,
        "payment_method": "CARD",
        "configuration_version": 1,
        "displayed_price_minor": 1000,
        "test_scenario": "TEST_SUCCESS",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/api/v1/device/payments", headers=device_headers("bench-card-success"), json=body
        )
        second = await client.post(
            "/api/v1/device/payments", headers=device_headers("bench-card-success"), json=body
        )
        conflict = await client.post(
            "/api/v1/device/payments",
            headers=device_headers("bench-card-success"),
            json={**body, "displayed_price_minor": 1500},
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert first.json()["data"]["status"] == "SUCCESS"
    assert first.json()["data"]["start_right"] is not None
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert int(
        await scalar(
            "SELECT count(*) FROM payment_transactions WHERE device_id=1 AND idempotency_key='bench-card-success'"
        )
    ) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_failed_card_payment_never_creates_start_right() -> None:
    await prepare_device()
    await execute("DELETE FROM payment_transactions WHERE idempotency_key='bench-card-failed'")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/device/payments",
            headers=device_headers("bench-card-failed"),
            json={
                "station_program_id": 1,
                "payment_method": "CARD",
                "configuration_version": 1,
                "displayed_price_minor": 1000,
                "test_scenario": "TEST_FAILED",
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CARD_DECLINED"
    payment_id = int(
        await scalar(
            "SELECT id FROM payment_transactions WHERE device_id=1 AND idempotency_key='bench-card-failed'"
        )
    )
    assert int(await scalar("SELECT count(*) FROM start_rights WHERE payment_id=:id", id=payment_id)) == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_single_use_qr_allows_exactly_one_concurrent_success() -> None:
    await prepare_device()
    await execute(
        """
        DELETE FROM payment_transactions WHERE idempotency_key LIKE 'bench-qr-%';
        UPDATE qr_codes SET usage_count=0, status='ACTIVE' WHERE id=1;
        """
    )
    body = {
        "payment_method": "QR",
        "configuration_version": 1,
        "qr_token": "qr-token-1",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            client.post("/api/v1/device/payments", headers=device_headers("bench-qr-a"), json=body),
            client.post("/api/v1/device/payments", headers=device_headers("bench-qr-b"), json=body),
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert int(await scalar("SELECT usage_count FROM qr_codes WHERE id=1")) == 1
    assert await scalar("SELECT status FROM qr_codes WHERE id=1") == "USED"
    assert int(
        await scalar(
            "SELECT count(*) FROM payment_transactions WHERE qr_code_id=1 AND idempotency_key LIKE 'bench-qr-%' AND status='SUCCESS'"
        )
    ) == 1
    assert int(
        await scalar(
            "SELECT count(*) FROM start_rights sr JOIN payment_transactions p ON p.id=sr.payment_id WHERE p.idempotency_key LIKE 'bench-qr-%'"
        )
    ) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_rf_wallet_with_one_purchase_funds_exactly_one_concurrent_request() -> None:
    await prepare_device()
    await execute(
        """
        DELETE FROM payment_transactions WHERE idempotency_key LIKE 'bench-rf-%';
        UPDATE rf_wallets SET balance_minor=1000, version=0, updated_at=now() WHERE id=1;
        """
    )
    body = {
        "station_program_id": 1,
        "payment_method": "RF_CARD",
        "configuration_version": 1,
        "displayed_price_minor": 1000,
        "rf_uid": "AABBCCDD00000001",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(
            client.post("/api/v1/device/payments", headers=device_headers("bench-rf-a"), json=body),
            client.post("/api/v1/device/payments", headers=device_headers("bench-rf-b"), json=body),
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert int(await scalar("SELECT balance_minor FROM rf_wallets WHERE id=1")) == 0
    assert int(await scalar("SELECT version FROM rf_wallets WHERE id=1")) == 1
    assert int(
        await scalar(
            "SELECT count(*) FROM rf_wallet_ledger l JOIN payment_transactions p ON p.id=l.payment_id WHERE p.idempotency_key LIKE 'bench-rf-%' AND l.direction='DEBIT'"
        )
    ) == 1
    assert int(
        await scalar(
            "SELECT count(*) FROM payment_transactions WHERE idempotency_key LIKE 'bench-rf-%' AND status='SUCCESS'"
        )
    ) == 1
