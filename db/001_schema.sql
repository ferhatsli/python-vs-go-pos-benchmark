\set ON_ERROR_STOP on

CREATE TABLE companies (
    id BIGINT PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE panel_users (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    token_hash TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE stations (
    id BIGINT PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    external_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE devices (
    id BIGINT PRIMARY KEY,
    station_id BIGINT NOT NULL REFERENCES stations(id),
    external_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','INACTIVE','BLOCKED')),
    monitoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    offline_threshold_seconds INTEGER NOT NULL DEFAULT 90 CHECK (offline_threshold_seconds > 0)
);

CREATE TABLE device_credentials (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    credential_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','REVOKED')),
    issued_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    UNIQUE (device_id, credential_hash)
);

CREATE TABLE device_configurations (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('PUBLISHED','SUPERSEDED')),
    checksum TEXT NOT NULL,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (device_id, version)
);

CREATE TABLE device_current_states (
    device_id BIGINT PRIMARY KEY REFERENCES devices(id),
    last_seen_at TIMESTAMPTZ,
    app_version TEXT,
    state_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_configuration_version INTEGER,
    acknowledged_configuration_version INTEGER,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE device_heartbeats (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    sequence BIGINT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE programs (
    id BIGINT PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    external_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    price_minor BIGINT NOT NULL CHECK (price_minor >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE program_payment_methods (
    id BIGSERIAL PRIMARY KEY,
    program_id BIGINT NOT NULL REFERENCES programs(id),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('CARD','QR','RF_CARD')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (program_id, payment_method)
);

CREATE TABLE entitlements (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    program_id BIGINT NOT NULL REFERENCES programs(id),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (device_id, program_id)
);

CREATE TABLE wash_bays (
    id BIGINT PRIMARY KEY,
    station_id BIGINT NOT NULL REFERENCES stations(id),
    device_id BIGINT UNIQUE REFERENCES devices(id),
    external_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('IDLE','BUSY','OFFLINE'))
);

CREATE TABLE maintenance_windows (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT REFERENCES devices(id),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('SCHEDULED','ACTIVE','COMPLETED','CANCELLED')),
    CHECK (ends_at > starts_at)
);

CREATE TABLE qr_codes (
    id BIGSERIAL PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    station_id BIGINT NOT NULL REFERENCES stations(id),
    program_id BIGINT NOT NULL REFERENCES programs(id),
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'TRY',
    usage_limit INTEGER NOT NULL CHECK (usage_limit > 0),
    usage_count INTEGER NOT NULL DEFAULT 0 CHECK (usage_count >= 0 AND usage_count <= usage_limit),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','USED','EXPIRED')),
    starts_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE rf_cards (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    uid_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','BLOCKED')),
    expires_at TIMESTAMPTZ
);

CREATE TABLE rf_wallets (
    id BIGSERIAL PRIMARY KEY,
    rf_card_id BIGINT NOT NULL UNIQUE REFERENCES rf_cards(id),
    balance_minor BIGINT NOT NULL CHECK (balance_minor >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE payment_transactions (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    station_id BIGINT NOT NULL REFERENCES stations(id),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('CARD','QR','RF_CARD')),
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'TRY',
    status TEXT NOT NULL CHECK (status IN ('PENDING','SUCCESS','FAILED','CANCELLED')),
    error_code TEXT,
    error_message TEXT,
    program_id BIGINT REFERENCES programs(id),
    qr_code_id BIGINT REFERENCES qr_codes(id),
    rf_wallet_id BIGINT REFERENCES rf_wallets(id),
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    UNIQUE (device_id, idempotency_key)
);

CREATE TABLE payment_attempts (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL REFERENCES payment_transactions(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    status TEXT NOT NULL CHECK (status IN ('PENDING','SUCCESS','FAILED','CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (payment_id, attempt_no)
);

CREATE TABLE provider_transactions (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL UNIQUE REFERENCES payment_transactions(id) ON DELETE CASCADE,
    provider_ref TEXT UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('PENDING','SUCCESS','FAILED','CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE start_rights (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL UNIQUE REFERENCES payment_transactions(id) ON DELETE CASCADE,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    wash_bay_id BIGINT REFERENCES wash_bays(id),
    program_id BIGINT REFERENCES programs(id),
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE','CONSUMED','CANCELLED','EXPIRED')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE rf_wallet_ledger (
    id BIGSERIAL PRIMARY KEY,
    wallet_id BIGINT NOT NULL REFERENCES rf_wallets(id),
    payment_id BIGINT REFERENCES payment_transactions(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK (direction IN ('DEBIT','CREDIT')),
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (payment_id, direction)
);

CREATE TABLE program_executions (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL UNIQUE REFERENCES payment_transactions(id) ON DELETE CASCADE,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    wash_bay_id BIGINT REFERENCES wash_bays(id),
    program_id BIGINT REFERENCES programs(id),
    status TEXT NOT NULL CHECK (status IN ('CREATED','COMMAND_SENT','RUNNING','SUCCESS','FAILED','TIMEOUT','CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE commands (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    program_execution_id BIGINT NOT NULL REFERENCES program_executions(id) ON DELETE CASCADE,
    command_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING','SENT','ACKNOWLEDGED','SUCCESS','FAILED')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    result_code TEXT,
    UNIQUE (device_id, command_key)
);

CREATE TABLE command_results (
    id BIGSERIAL PRIMARY KEY,
    command_id BIGINT NOT NULL UNIQUE REFERENCES commands(id) ON DELETE CASCADE,
    result_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('SUCCESS','FAILED')),
    code TEXT,
    message TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (command_id, result_key)
);

CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT REFERENCES devices(id),
    payment_id BIGINT REFERENCES payment_transactions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE audit_entries (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT REFERENCES payment_transactions(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE alarms (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT NOT NULL REFERENCES devices(id),
    alarm_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN','RESOLVED')),
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ
);
