from __future__ import annotations

import asyncio
import json
from time import perf_counter

from app.db import close_database, get_session_factory
from app.worker import sweep_target_runtime


async def run_once() -> None:
    started = perf_counter()
    async with get_session_factory()() as session:
        result = await sweep_target_runtime(session)
    duration_ms = (perf_counter() - started) * 1000.0
    devices = int(result["devices_evaluated"])
    payload = {
        **result,
        "duration_ms": duration_ms,
        "devices_per_second": devices / (duration_ms / 1000.0) if duration_ms > 0 else 0.0,
        "overrun_5s": duration_ms > 5000.0,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    await close_database()


if __name__ == "__main__":
    asyncio.run(run_once())
