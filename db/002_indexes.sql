\set ON_ERROR_STOP on

CREATE INDEX idx_devices_station_status ON devices(station_id, status);
CREATE UNIQUE INDEX uq_device_credentials_active ON device_credentials(device_id) WHERE status = 'ACTIVE';
CREATE INDEX idx_device_credentials_lookup ON device_credentials(device_id, credential_hash, status);
CREATE INDEX idx_device_configurations_published ON device_configurations(device_id, status, version DESC);
CREATE INDEX idx_device_current_states_monitoring ON device_current_states(last_seen_at);
CREATE INDEX idx_device_heartbeats_device_occurred ON device_heartbeats(device_id, occurred_at DESC);
CREATE INDEX idx_device_heartbeats_occurred ON device_heartbeats(occurred_at DESC);
CREATE INDEX idx_payment_transactions_station_created ON payment_transactions(station_id, created_at DESC);
CREATE INDEX idx_payment_transactions_status_created ON payment_transactions(status, created_at DESC);
CREATE INDEX idx_payment_transactions_method_created ON payment_transactions(method, created_at DESC);
CREATE INDEX idx_payment_attempts_payment ON payment_attempts(payment_id);
CREATE INDEX idx_rf_wallet_ledger_wallet_created ON rf_wallet_ledger(wallet_id, created_at DESC);
CREATE INDEX idx_commands_device_status ON commands(device_id, status, created_at DESC);
CREATE UNIQUE INDEX uq_alarms_open_device_key ON alarms(device_id, alarm_key) WHERE status = 'OPEN';
CREATE INDEX idx_alarms_opened ON alarms(status, opened_at DESC);
