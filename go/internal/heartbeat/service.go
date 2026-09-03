package heartbeat

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func Record(ctx context.Context, pool *pgxpool.Pool, deviceID int64, sequence *int64, appVersion *string, state map[string]any) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	now := time.Now().UTC()
	payload, err := json.Marshal(state)
	if err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, `
		INSERT INTO device_heartbeats (device_id, occurred_at, received_at, sequence, payload)
		VALUES ($1,$2,$2,$3,$4::jsonb)
	`, deviceID, now, sequence, payload); err != nil {
		return err
	}

	var current int64
	err = tx.QueryRow(ctx, `SELECT device_id FROM device_current_states WHERE device_id=$1`, deviceID).Scan(&current)
	if err != nil {
		if _, err = tx.Exec(ctx, `
			INSERT INTO device_current_states (device_id,state_payload,updated_at)
			VALUES ($1,'{}'::jsonb,$2)
		`, deviceID, now); err != nil {
			return err
		}
	}
	if _, err = tx.Exec(ctx, `
		UPDATE device_current_states
		SET last_seen_at=$2, app_version=$3, state_payload=$4::jsonb, updated_at=$2
		WHERE device_id=$1
	`, deviceID, now, appVersion, payload); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
