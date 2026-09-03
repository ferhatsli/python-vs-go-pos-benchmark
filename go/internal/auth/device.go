package auth

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"

	"github.com/jackc/pgx/v5"
)

type Querier interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

type Device struct {
	ID          int64
	StationID   int64
	ExternalKey string
	Status      string
}

var ErrInvalidDeviceCredential = errors.New("invalid device credential")

func Token(authorization string) string {
	if !strings.HasPrefix(authorization, "Device ") {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(authorization, "Device "))
}

func AuthenticateDevice(ctx context.Context, q Querier, deviceID int64, token string) (Device, error) {
	digest := sha256.Sum256([]byte(token))
	tokenHash := hex.EncodeToString(digest[:])
	var credentialID int64
	credentialErr := q.QueryRow(ctx, `
		SELECT id
		FROM device_credentials
		WHERE device_id=$1 AND credential_hash=$2 AND status='ACTIVE'
		LIMIT 1
	`, deviceID, tokenHash).Scan(&credentialID)

	var d Device
	deviceErr := q.QueryRow(ctx, `
		SELECT id, station_id, external_key, status
		FROM devices
		WHERE id=$1
	`, deviceID).Scan(&d.ID, &d.StationID, &d.ExternalKey, &d.Status)

	if credentialErr != nil || deviceErr != nil || d.Status != "ACTIVE" {
		return Device{}, ErrInvalidDeviceCredential
	}
	return d, nil
}
