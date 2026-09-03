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


async def scalar(sql: str) -> object:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(text(sql))
    finally:
        await engine.dispose()


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_rejects_invalid_panel_token() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/dashboard/overview?period=TODAY",
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_PANEL_CREDENTIAL"


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_is_company_scoped_and_matches_dataset_snapshot() -> None:
    expected_transactions = int(
        await scalar(
            """
            SELECT count(*) FROM payment_transactions p
            JOIN stations s ON s.id=p.station_id
            WHERE s.company_id=1 AND p.created_at >= TIMESTAMPTZ '2026-08-31 00:00:00+00'
              AND p.created_at < TIMESTAMPTZ '2026-09-01 00:00:00+00'
            """
        )
    )
    expected_success = int(
        await scalar(
            """
            SELECT count(*) FROM payment_transactions p
            JOIN stations s ON s.id=p.station_id
            WHERE s.company_id=1 AND p.status='SUCCESS'
              AND p.created_at >= TIMESTAMPTZ '2026-08-31 00:00:00+00'
              AND p.created_at < TIMESTAMPTZ '2026-09-01 00:00:00+00'
            """
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/dashboard/overview?period=TODAY",
            headers={"Authorization": "Bearer panel-company-1"},
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["period"] == "TODAY"
    assert data["workspace_company"]["id"] == "1"
    assert data["organization"] == {
        "dealer_count": 0,
        "company_count": 1,
        "station_count": 5,
        "wash_bay_count": 50,
    }
    assert data["devices"]["total"] == 50
    assert data["financial"]["transaction_count"] == expected_transactions
    assert data["financial"]["successful_transaction_count"] == expected_success
    assert data["financial"]["currency"] == "TRY"
    assert len(data["payment_methods"]) <= 3
