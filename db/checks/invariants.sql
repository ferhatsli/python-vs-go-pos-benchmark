\set ON_ERROR_STOP on

-- Every invariant query must return zero rows.

-- No duplicate payment idempotency tuple.
SELECT device_id, idempotency_key, count(*) AS duplicate_count
FROM payment_transactions
GROUP BY device_id, idempotency_key
HAVING count(*) > 1;

-- No negative RF wallet balance.
SELECT id, balance_minor
FROM rf_wallets
WHERE balance_minor < 0;

-- No QR over-consumption.
SELECT id, usage_count, usage_limit
FROM qr_codes
WHERE usage_count > usage_limit;

-- A successful payment can create at most one start right.
SELECT payment_id, count(*) AS start_right_count
FROM start_rights
GROUP BY payment_id
HAVING count(*) > 1;

-- A payment can debit an RF wallet at most once.
SELECT payment_id, count(*) AS debit_count
FROM rf_wallet_ledger
WHERE direction = 'DEBIT'
GROUP BY payment_id
HAVING count(*) > 1;

-- A command can have at most one terminal result.
SELECT command_id, count(*) AS result_count
FROM command_results
GROUP BY command_id
HAVING count(*) > 1;

-- Terminal commands cannot be completed without acknowledgement.
SELECT id, status
FROM commands
WHERE status IN ('SUCCESS', 'FAILED')
  AND acknowledged_at IS NULL;

-- Only one open alarm per device/alarm key.
SELECT device_id, alarm_key, count(*) AS open_alarm_count
FROM alarms
WHERE status = 'OPEN'
GROUP BY device_id, alarm_key
HAVING count(*) > 1;

-- One idempotency tuple cannot contain multiple request hashes.
SELECT device_id, idempotency_key, count(DISTINCT request_hash) AS request_hash_count
FROM payment_transactions
GROUP BY device_id, idempotency_key
HAVING count(DISTINCT request_hash) > 1;

-- Terminal command and execution states must agree.
SELECT c.id AS command_id, c.status AS command_status, e.status AS execution_status
FROM commands c
JOIN program_executions e ON e.id = c.program_execution_id
WHERE c.status IN ('SUCCESS', 'FAILED') AND e.status <> c.status;

-- Correctness-run successful financial state must be fully committed.
SELECT p.id, p.method, p.status
FROM payment_transactions p
WHERE p.idempotency_key LIKE 'corr-%'
  AND (
    (p.status = 'SUCCESS' AND NOT EXISTS (SELECT 1 FROM start_rights sr WHERE sr.payment_id = p.id))
    OR
    (p.status = 'SUCCESS' AND p.method = 'RF_CARD' AND NOT EXISTS (
      SELECT 1 FROM rf_wallet_ledger l
      WHERE l.payment_id = p.id AND l.direction = 'DEBIT'
    ))
  );
