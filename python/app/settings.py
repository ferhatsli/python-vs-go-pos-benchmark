from __future__ import annotations

import os

DATABASE_URL = os.environ.get(
    "BENCH_DATABASE_URL",
    "postgresql+asyncpg://benchmark:benchmark-local-only@postgres:5432/pos_benchmark",
)
DEVICE_HEARTBEAT_SECONDS = 30
DB_POOL_SIZE = 40
DB_MAX_OVERFLOW = 0
CSRF_SECRET = "benchmark-csrf-secret"
QR_PEPPER = "benchmark-qr-pepper"
