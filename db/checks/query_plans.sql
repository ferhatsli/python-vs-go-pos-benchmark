\set ON_ERROR_STOP on

EXPLAIN (ANALYZE, BUFFERS, WAL)
SELECT * FROM devices WHERE id = 1;

EXPLAIN (ANALYZE, BUFFERS, WAL)
SELECT * FROM payment_transactions
WHERE device_id = 1 AND idempotency_key = 'idem-000000000001';

EXPLAIN (ANALYZE, BUFFERS, WAL)
SELECT station_id, count(*) AS payment_count, sum(amount_minor) AS amount_minor
FROM payment_transactions
WHERE created_at >= TIMESTAMPTZ '2026-08-31 00:00:00+00'
GROUP BY station_id
ORDER BY station_id;

EXPLAIN (ANALYZE, BUFFERS, WAL)
SELECT d.id, s.last_seen_at
FROM devices d
LEFT JOIN device_current_states s ON s.device_id = d.id
WHERE d.monitoring_enabled = TRUE
ORDER BY d.id;
