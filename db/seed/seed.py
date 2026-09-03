from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from profiles import PROFILES, SEED, get_profile

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILES = [
    ROOT / "db" / "003_extensions.sql",
    ROOT / "db" / "001_schema.sql",
    ROOT / "db" / "002_indexes.sql",
]
FIXED_TS = "2026-08-31 00:00:00+00"
QR_PEPPER = "benchmark-qr-pepper"


def schema_hash() -> str:
    digest = hashlib.sha256()
    for path in SCHEMA_FILES:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def compose_psql_args(*extra: str) -> list[str]:
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-X",
        "-qAt",
        "-U",
        "benchmark",
        "-d",
        "pos_benchmark",
        "-v",
        "ON_ERROR_STOP=1",
        *extra,
    ]


def run_psql(sql: str) -> str:
    result = subprocess.run(
        compose_psql_args("-c", sql),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "psql failed")
    return result.stdout.strip()


def seed_sql(profile: str) -> str:
    cfg = get_profile(profile)
    c, s, d, p = cfg["companies"], cfg["stations"], cfg["devices"], cfg["payments"]
    qr = max(100, d // 5)
    wallets = max(100, d // 5)
    commands = max(10, d // 10)
    return f"""
BEGIN;
TRUNCATE TABLE
  command_results, commands, program_executions, alarms, maintenance_windows,
  audit_entries, events, rf_wallet_ledger, start_rights, provider_transactions,
  payment_attempts, payment_transactions, rf_wallets, rf_cards, qr_codes,
  wash_bays, entitlements, program_payment_methods, programs, device_heartbeats,
  device_current_states, device_configurations, device_credentials,
  devices, stations, panel_users, companies
RESTART IDENTITY CASCADE;

INSERT INTO companies (id, external_key, name)
SELECT g, 'cmp-' || lpad(g::text, 6, '0'), format('Company %s', g)
FROM generate_series(1, {c}) AS g;

INSERT INTO panel_users (company_id, token_hash, active)
SELECT g,
       encode(digest('panel-company-' || g::text, 'sha256'), 'hex'),
       TRUE
FROM generate_series(1, {c}) AS g;

INSERT INTO stations (id, company_id, external_key, name)
SELECT g,
       ((g - 1) % {c}) + 1,
       'stn-' || lpad(g::text, 6, '0'),
       format('Station %s', g)
FROM generate_series(1, {s}) AS g;

INSERT INTO devices (id, station_id, external_key, status, monitoring_enabled, offline_threshold_seconds)
SELECT g,
       ((g - 1) % {s}) + 1,
       'dev-' || lpad(g::text, 7, '0'),
       'ACTIVE',
       TRUE,
       90
FROM generate_series(1, {d}) AS g;

INSERT INTO device_credentials (device_id, credential_hash, status, issued_at)
SELECT id,
       encode(digest('credential-' || id::text, 'sha256'), 'hex'),
       'ACTIVE',
       TIMESTAMPTZ '{FIXED_TS}'
FROM devices ORDER BY id;

INSERT INTO device_configurations (device_id, version, status, checksum, snapshot, created_at)
SELECT d.id,
       1,
       'PUBLISHED',
       md5('configuration-' || d.id::text || '-1'),
       jsonb_build_object(
         'device_id', d.external_key,
         'station_id', s.external_key,
         'heartbeat_seconds', 30,
         'currency', 'TRY'
       ),
       TIMESTAMPTZ '{FIXED_TS}'
FROM devices d JOIN stations s ON s.id = d.station_id
ORDER BY d.id;

INSERT INTO device_current_states (
  device_id, last_seen_at, app_version, state_payload,
  current_configuration_version, acknowledged_configuration_version, updated_at
)
SELECT id,
       TIMESTAMPTZ '{FIXED_TS}' + ((id % 60) * INTERVAL '1 second'),
       '1.0.0',
       '{{}}'::jsonb,
       1,
       1,
       TIMESTAMPTZ '{FIXED_TS}' + ((id % 60) * INTERVAL '1 second')
FROM devices ORDER BY id;

INSERT INTO device_heartbeats (device_id, occurred_at, received_at, sequence, payload)
SELECT id,
       TIMESTAMPTZ '{FIXED_TS}' + ((id % 60) * INTERVAL '1 second'),
       TIMESTAMPTZ '{FIXED_TS}' + ((id % 60) * INTERVAL '1 second'),
       id,
       '{{}}'::jsonb
FROM devices ORDER BY id;

INSERT INTO programs (id, company_id, external_key, name, price_minor, active)
SELECT g,
       ((g - 1) / 3) + 1,
       'prg-' || lpad(g::text, 6, '0'),
       format('Program %s', g),
       1000 + ((g - 1) % 3) * 500,
       TRUE
FROM generate_series(1, {c * 3}) AS g;

INSERT INTO program_payment_methods (program_id, payment_method, enabled)
SELECT p.id, method, TRUE
FROM programs p
CROSS JOIN (VALUES ('CARD'), ('QR'), ('RF_CARD')) AS methods(method);

INSERT INTO entitlements (device_id, program_id, enabled)
SELECT d.id, ((s.company_id - 1) * 3) + 1, TRUE
FROM devices d JOIN stations s ON s.id = d.station_id;

INSERT INTO wash_bays (id, station_id, device_id, external_key, status)
SELECT id, station_id, id, 'bay-' || lpad(id::text, 7, '0'), 'IDLE'
FROM devices;

WITH src AS (
  SELECT g,
         ((g - 1) % {s}) + 1 AS station_id
  FROM generate_series(1, {qr}) AS g
), scoped AS (
  SELECT src.g, src.station_id, st.company_id,
         ((st.company_id - 1) * 3) + 1 AS program_id
  FROM src JOIN stations st ON st.id = src.station_id
)
INSERT INTO qr_codes (
  token_hash, company_id, station_id, program_id, amount_minor, currency,
  usage_limit, usage_count, status, starts_at, expires_at
)
SELECT encode(hmac('qr-token-' || g::text, '{QR_PEPPER}', 'sha256'), 'hex'),
       company_id,
       station_id,
       program_id,
       1500,
       'TRY',
       1,
       0,
       'ACTIVE',
       TIMESTAMPTZ '{FIXED_TS}',
       TIMESTAMPTZ '2027-12-31 23:59:59+00'
FROM scoped ORDER BY g;

INSERT INTO rf_cards (company_id, uid_hash, status, expires_at)
SELECT ((g - 1) % {c}) + 1,
       encode(
         hmac(upper('AABBCCDD' || lpad(to_hex(g), 8, '0')), '{QR_PEPPER}', 'sha256'),
         'hex'
       ),
       'ACTIVE',
       TIMESTAMPTZ '2027-12-31 23:59:59+00'
FROM generate_series(1, {wallets}) AS g;

INSERT INTO rf_wallets (rf_card_id, balance_minor, version, updated_at)
SELECT id, 1000, 0, TIMESTAMPTZ '{FIXED_TS}'
FROM rf_cards ORDER BY id;

WITH src AS (
  SELECT g AS id,
         ((g - 1) % {d}) + 1 AS device_id,
         ((g - 1) % {s}) + 1 AS station_id
  FROM generate_series(1, {p}) AS g
), enriched AS (
  SELECT src.*,
         ((st.company_id - 1) * 3) + ((src.id - 1) % 3) + 1 AS program_id
  FROM src JOIN stations st ON st.id = src.station_id
)
INSERT INTO payment_transactions (
  id, device_id, station_id, idempotency_key, request_hash, method,
  amount_minor, currency, status, program_id, created_at, completed_at
)
SELECT id,
       device_id,
       station_id,
       'idem-' || lpad(id::text, 12, '0'),
       md5('request-' || id::text),
       CASE id % 3 WHEN 0 THEN 'CARD' WHEN 1 THEN 'QR' ELSE 'RF_CARD' END,
       1000 + ((id % 20) * 100),
       'TRY',
       CASE WHEN id % 20 = 0 THEN 'FAILED' ELSE 'SUCCESS' END,
       program_id,
       TIMESTAMPTZ '{FIXED_TS}' + ((id % 86400) * INTERVAL '1 second'),
       TIMESTAMPTZ '{FIXED_TS}' + ((id % 86400) * INTERVAL '1 second') + INTERVAL '250 milliseconds'
FROM enriched;

SELECT setval('payment_transactions_id_seq', GREATEST({p}, 1), TRUE);

INSERT INTO program_executions (
  id, payment_id, device_id, wash_bay_id, program_id, status, created_at
)
SELECT g,
       g,
       p.device_id,
       p.device_id,
       p.program_id,
       'CREATED',
       TIMESTAMPTZ '{FIXED_TS}' + ((g % 3600) * INTERVAL '1 second')
FROM generate_series(1, {commands}) AS g
JOIN payment_transactions p ON p.id = g;
SELECT setval('program_executions_id_seq', GREATEST({commands}, 1), TRUE);

INSERT INTO commands (
  id, device_id, program_execution_id, command_key, status, payload, created_at
)
SELECT g,
       e.device_id,
       e.id,
       'cmd-' || lpad(g::text, 8, '0'),
       'PENDING',
       '{{}}'::jsonb,
       TIMESTAMPTZ '{FIXED_TS}' + ((g % 3600) * INTERVAL '1 second')
FROM generate_series(1, {commands}) AS g
JOIN program_executions e ON e.id = g;
SELECT setval('commands_id_seq', GREATEST({commands}, 1), TRUE);

COMMIT;
ANALYZE;
"""


def seed_database(profile: str) -> None:
    run_psql(seed_sql(profile))


def row_counts() -> dict[str, int]:
    raw = run_psql("""
SELECT json_build_object(
  'companies', (SELECT count(*) FROM companies),
  'panel_users', (SELECT count(*) FROM panel_users),
  'stations', (SELECT count(*) FROM stations),
  'devices', (SELECT count(*) FROM devices),
  'device_credentials', (SELECT count(*) FROM device_credentials),
  'device_configurations', (SELECT count(*) FROM device_configurations),
  'device_current_states', (SELECT count(*) FROM device_current_states),
  'payments', (SELECT count(*) FROM payment_transactions),
  'qr_codes', (SELECT count(*) FROM qr_codes),
  'rf_cards', (SELECT count(*) FROM rf_cards),
  'rf_wallets', (SELECT count(*) FROM rf_wallets),
  'program_executions', (SELECT count(*) FROM program_executions),
  'commands', (SELECT count(*) FROM commands),
  'heartbeats', (SELECT count(*) FROM device_heartbeats)
)::text;
""")
    return {k: int(v) for k, v in json.loads(raw).items()}


def stable_keys_sha256() -> str:
    sql = """
COPY (
  SELECT stable_key FROM (
    SELECT 'company:' || external_key AS stable_key FROM companies
    UNION ALL SELECT 'panel:' || id::text || ':' || company_id::text || ':' || token_hash FROM panel_users
    UNION ALL SELECT 'station:' || external_key FROM stations
    UNION ALL SELECT 'device:' || external_key FROM devices
    UNION ALL SELECT 'credential:' || device_id::text || ':' || credential_hash || ':' || status FROM device_credentials
    UNION ALL SELECT 'configuration:' || device_id::text || ':' || version::text || ':' || checksum FROM device_configurations
    UNION ALL SELECT 'current-state:' || device_id::text || ':' || coalesce(current_configuration_version::text, '') || ':' || coalesce(acknowledged_configuration_version::text, '') FROM device_current_states
    UNION ALL SELECT 'program:' || external_key FROM programs
    UNION ALL SELECT 'method:' || program_id::text || ':' || payment_method FROM program_payment_methods
    UNION ALL SELECT 'payment:' || device_id::text || ':' || idempotency_key FROM payment_transactions
    UNION ALL SELECT 'qr:' || id::text || ':' || token_hash FROM qr_codes
    UNION ALL SELECT 'rf-card:' || id::text || ':' || uid_hash FROM rf_cards
    UNION ALL SELECT 'wallet:' || id::text || ':' || rf_card_id::text FROM rf_wallets
    UNION ALL SELECT 'execution:' || id::text || ':' || payment_id::text FROM program_executions
    UNION ALL SELECT 'command:' || device_id::text || ':' || command_key FROM commands
  ) AS keys
  ORDER BY stable_key
) TO STDOUT;
"""
    proc = subprocess.Popen(
        compose_psql_args("-c", sql),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    digest = hashlib.sha256()
    for chunk in iter(lambda: proc.stdout.read(1024 * 1024), b""):
        digest.update(chunk)
    stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(stderr.strip() or "fingerprint COPY failed")
    return digest.hexdigest()


def fingerprint(profile: str) -> dict[str, object]:
    return {
        "seed": SEED,
        "profile": profile,
        "schema_hash": schema_hash(),
        "stable_keys_sha256": stable_keys_sha256(),
        "row_counts": row_counts(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILES))
    parser.add_argument("--describe-profile", choices=sorted(PROFILES))
    parser.add_argument("--describe-all", action="store_true")
    parser.add_argument("--schema-hash", action="store_true")
    parser.add_argument("--fingerprint-only", action="store_true")
    args = parser.parse_args()

    if args.describe_profile:
        print(
            json.dumps(
                {"seed": SEED, "profile": args.describe_profile, **get_profile(args.describe_profile)},
                sort_keys=True,
            )
        )
        return 0
    if args.describe_all:
        print(json.dumps(PROFILES, sort_keys=True))
        return 0
    if args.schema_hash:
        print(schema_hash())
        return 0
    if not args.profile:
        parser.error("--profile is required for seed/fingerprint")

    try:
        if not args.fingerprint_only:
            seed_database(args.profile)
        print(json.dumps(fingerprint(args.profile), sort_keys=True))
        return 0
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
