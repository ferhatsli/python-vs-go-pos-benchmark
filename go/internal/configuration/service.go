package configuration

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("configuration not found")

func Get(ctx context.Context, pool *pgxpool.Pool, deviceID int64, currentVersion *int) (map[string]any, error) {
	var id int64
	var version int
	var checksum string
	var raw []byte
	err := pool.QueryRow(ctx, `
		SELECT id, version, checksum, snapshot
		FROM device_configurations
		WHERE device_id=$1 AND status='PUBLISHED'
	`, deviceID).Scan(&id, &version, &checksum, &raw)
	if err != nil {
		return nil, ErrNotFound
	}
	var snapshot map[string]any
	if err := json.Unmarshal(raw, &snapshot); err != nil {
		return nil, err
	}
	result := map[string]any{
		"id":               id,
		"version":          version,
		"checksum":         checksum,
		"update_available": currentVersion == nil || *currentVersion != version,
	}
	for k, v := range snapshot {
		result[k] = v
	}
	return result, nil
}
