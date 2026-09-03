from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.http import AppError


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return ""
    return authorization.removeprefix("Bearer ").strip()


async def authenticate_panel(session: AsyncSession, token: str) -> dict[str, object]:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    result = await session.execute(
        text(
            """
            SELECT id, company_id FROM panel_users
            WHERE token_hash=:token_hash AND active=TRUE
            """
        ),
        {"token_hash": token_hash},
    )
    row = result.mappings().first()
    if row is None:
        raise AppError(401, "INVALID_PANEL_CREDENTIAL", "Panel kimliği doğrulanamadı.")
    return dict(row)


def period_bounds(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "TODAY":
        return today, today + timedelta(days=1)
    if period == "LAST_7_DAYS":
        return today - timedelta(days=6), today + timedelta(days=1)
    if period == "THIS_MONTH":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    raise AppError(422, "INVALID_PERIOD", "Dashboard dönemi geçersiz.")


async def overview(session: AsyncSession, company_id: int, period: str) -> dict[str, object]:
    start, end = period_bounds(period)
    company = (
        await session.execute(
            text("SELECT id, name FROM companies WHERE id=:company_id"),
            {"company_id": company_id},
        )
    ).mappings().first()
    if company is None:
        raise AppError(404, "COMPANY_NOT_FOUND", "Şirket bulunamadı.")

    organization = (
        await session.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM stations WHERE company_id=:company_id) AS station_count,
                  (SELECT count(*) FROM wash_bays wb JOIN stations s ON s.id=wb.station_id
                   WHERE s.company_id=:company_id) AS wash_bay_count
                """
            ),
            {"company_id": company_id},
        )
    ).mappings().one()

    now = datetime.now(UTC)
    devices = (
        await session.execute(
            text(
                """
                SELECT
                  count(d.id) AS total,
                  count(d.id) FILTER (WHERE cs.last_seen_at >= :online_cutoff) AS online,
                  count(d.id) FILTER (WHERE cs.last_seen_at < :online_cutoff) AS offline,
                  count(d.id) FILTER (WHERE cs.last_seen_at IS NULL) AS unknown,
                  count(d.id) FILTER (WHERE d.status='ACTIVE') AS active
                FROM devices d
                JOIN stations s ON s.id=d.station_id
                LEFT JOIN device_current_states cs ON cs.device_id=d.id
                WHERE s.company_id=:company_id
                """
            ),
            {"company_id": company_id, "online_cutoff": now - timedelta(seconds=120)},
        )
    ).mappings().one()

    financial = (
        await session.execute(
            text(
                """
                SELECT
                  count(p.id) AS transaction_count,
                  count(p.id) FILTER (WHERE p.status='SUCCESS') AS successful_transaction_count,
                  count(p.id) FILTER (WHERE p.status='FAILED') AS failed_transaction_count,
                  count(p.id) FILTER (WHERE p.status='PENDING') AS pending_transaction_count,
                  count(p.id) FILTER (WHERE p.status='CANCELLED') AS cancelled_transaction_count,
                  coalesce(sum(p.amount_minor) FILTER (WHERE p.status='SUCCESS'), 0) AS gross_amount
                FROM payment_transactions p
                JOIN stations s ON s.id=p.station_id
                WHERE s.company_id=:company_id AND p.created_at >= :start AND p.created_at < :end
                """
            ),
            {"company_id": company_id, "start": start, "end": end},
        )
    ).mappings().one()

    methods_result = await session.execute(
        text(
            """
            SELECT p.method,
                   count(*) AS total_count,
                   count(*) FILTER (WHERE p.status='SUCCESS') AS successful_count,
                   coalesce(sum(p.amount_minor) FILTER (WHERE p.status='SUCCESS'), 0) AS amount
            FROM payment_transactions p
            JOIN stations s ON s.id=p.station_id
            WHERE s.company_id=:company_id AND p.created_at >= :start AND p.created_at < :end
            GROUP BY p.method
            ORDER BY p.method
            """
        ),
        {"company_id": company_id, "start": start, "end": end},
    )
    method_rows = methods_result.mappings().all()

    failed_execution_count = int(
        await session.scalar(
            text(
                """
                SELECT count(e.id)
                FROM program_executions e
                JOIN payment_transactions p ON p.id=e.payment_id
                JOIN stations s ON s.id=p.station_id
                WHERE s.company_id=:company_id
                  AND e.created_at >= :start AND e.created_at < :end
                  AND e.status IN ('FAILED','TIMEOUT')
                """
            ),
            {"company_id": company_id, "start": start, "end": end},
        )
        or 0
    )

    gross = int(financial["gross_amount"] or 0)
    return {
        "period": period,
        "workspace_company": {"id": str(company["id"]), "name": str(company["name"])},
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "organization": {
            "dealer_count": 0,
            "company_count": 1,
            "station_count": int(organization["station_count"]),
            "wash_bay_count": int(organization["wash_bay_count"]),
        },
        "devices": {
            "total": int(devices["total"]),
            "online": int(devices["online"]),
            "offline": int(devices["offline"]),
            "unknown": int(devices["unknown"]),
            "active": int(devices["active"]),
            "suspended": 0,
        },
        "financial": {
            "transaction_count": int(financial["transaction_count"]),
            "successful_transaction_count": int(financial["successful_transaction_count"]),
            "failed_transaction_count": int(financial["failed_transaction_count"]),
            "pending_transaction_count": int(financial["pending_transaction_count"]),
            "cancelled_transaction_count": int(financial["cancelled_transaction_count"]),
            "gross_amount": gross,
            "refund_amount": 0,
            "net_amount": gross,
            "currency": "TRY",
        },
        "payment_methods": [
            {
                "payment_method": row["method"],
                "count": int(row["successful_count"]),
                "amount": int(row["amount"]),
                "total_count": int(row["total_count"]),
                "successful_count": int(row["successful_count"]),
            }
            for row in method_rows
        ],
        "failed_execution_count": failed_execution_count,
    }
