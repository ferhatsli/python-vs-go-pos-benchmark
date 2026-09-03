package commands

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

const csrfSecret = "benchmark-csrf-secret"

type AppError struct {
	Status  int
	Code    string
	Message string
}

func (e *AppError) Error() string { return e.Code }

type Item struct {
	ID               string         `json:"id"`
	ExecutionID      string         `json:"execution_id"`
	Type             string         `json:"type"`
	Status           string         `json:"status"`
	Payload          map[string]any `json:"payload"`
	CreatedAt        string         `json:"created_at"`
	SentAt           *string        `json:"sent_at"`
	AckDeadlineAt    string         `json:"ack_deadline_at"`
	ResultDeadlineAt *string        `json:"result_deadline_at"`
}

type commandRow struct {
	ID             int64
	ExecutionID    int64
	Status         string
	Payload        []byte
	CreatedAt      time.Time
	SentAt         *time.Time
	AcknowledgedAt *time.Time
	ResultCode     *string
}

func Pending(ctx context.Context, tx pgx.Tx, deviceID int64, limit int) ([]Item, error) {
	rows, err := tx.Query(ctx, `
SELECT id, program_execution_id, status, payload, created_at, sent_at, acknowledged_at
FROM commands
WHERE device_id=$1 AND status IN ('PENDING','SENT')
ORDER BY created_at, id
LIMIT $2`, deviceID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var buffered []commandRow
	for rows.Next() {
		var r commandRow
		if err := rows.Scan(&r.ID, &r.ExecutionID, &r.Status, &r.Payload, &r.CreatedAt, &r.SentAt, &r.AcknowledgedAt); err != nil {
			return nil, err
		}
		buffered = append(buffered, r)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	rows.Close()

	var items []Item
	now := time.Now().UTC()
	for _, r := range buffered {
		if r.Status == "PENDING" {
			if _, err := tx.Exec(ctx, `UPDATE commands SET status='SENT', sent_at=$1 WHERE id=$2`, now, r.ID); err != nil {
				return nil, err
			}
			if _, err := tx.Exec(ctx, `UPDATE program_executions SET status='COMMAND_SENT' WHERE id=$1 AND status='CREATED'`, r.ExecutionID); err != nil {
				return nil, err
			}
			r.Status = "SENT"
			r.SentAt = &now
		}
		payload := map[string]any{}
		_ = json.Unmarshal(r.Payload, &payload)
		created := r.CreatedAt.UTC()
		ackDeadline := created.Add(30 * time.Second).Format(time.RFC3339Nano)
		var sent *string
		if r.SentAt != nil {
			s := r.SentAt.UTC().Format(time.RFC3339Nano)
			sent = &s
		}
		var resultDeadline *string
		if r.AcknowledgedAt != nil {
			s := r.AcknowledgedAt.UTC().Add(120 * time.Second).Format(time.RFC3339Nano)
			resultDeadline = &s
		}
		items = append(items, Item{
			ID: fmt.Sprint(r.ID), ExecutionID: fmt.Sprint(r.ExecutionID), Type: "EXECUTE_PROGRAM", Status: r.Status,
			Payload: payload, CreatedAt: created.Format(time.RFC3339Nano), SentAt: sent,
			AckDeadlineAt: ackDeadline, ResultDeadlineAt: resultDeadline,
		})
	}
	return items, nil
}

func Acknowledge(ctx context.Context, tx pgx.Tx, deviceID, commandID int64) (map[string]any, error) {
	var r commandRow
	err := tx.QueryRow(ctx, `
SELECT id, program_execution_id, status, created_at, acknowledged_at, result_code
FROM commands WHERE id=$1 AND device_id=$2 FOR UPDATE`, commandID, deviceID).Scan(
		&r.ID, &r.ExecutionID, &r.Status, &r.CreatedAt, &r.AcknowledgedAt, &r.ResultCode,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, &AppError{404, "COMMAND_NOT_FOUND", "Komut bulunamadı."}
	}
	if err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	if (r.Status == "PENDING" || r.Status == "SENT") && !r.CreatedAt.After(now.Add(-30*time.Second)) {
		return nil, &AppError{409, "COMMAND_EXPIRED", "Komut onay süresi doldu."}
	}
	if r.Status == "PENDING" || r.Status == "SENT" {
		if _, err := tx.Exec(ctx, `UPDATE commands SET status='ACKNOWLEDGED', acknowledged_at=$1 WHERE id=$2`, now, commandID); err != nil {
			return nil, err
		}
		if _, err := tx.Exec(ctx, `UPDATE program_executions SET status='RUNNING', started_at=$1 WHERE id=$2`, now, r.ExecutionID); err != nil {
			return nil, err
		}
		r.Status = "ACKNOWLEDGED"
	} else if r.Status != "ACKNOWLEDGED" && r.Status != "SUCCESS" && r.Status != "FAILED" {
		return nil, &AppError{409, "COMMAND_NOT_ACKNOWLEDGEABLE", "Komut onaylanamaz."}
	}
	return map[string]any{"id": fmt.Sprint(r.ID), "status": r.Status}, nil
}

func resultHash(result string, code, message *string) string {
	c := "None"
	m := "None"
	if code != nil {
		c = *code
	}
	if message != nil {
		m = *message
	}
	raw := fmt.Sprintf("%s:%s:%s", result, c, m)
	h := hmac.New(sha256.New, []byte(csrfSecret))
	_, _ = h.Write([]byte(raw))
	return hex.EncodeToString(h.Sum(nil))
}

func ApplyResult(ctx context.Context, tx pgx.Tx, deviceID, commandID int64, result string, code, message *string, key string) (map[string]any, error) {
	if result != "SUCCESS" && result != "FAILED" {
		return nil, &AppError{422, "INVALID_COMMAND_RESULT", "Komut sonucu geçersiz."}
	}
	var r commandRow
	err := tx.QueryRow(ctx, `
SELECT id, program_execution_id, status, acknowledged_at, result_code
FROM commands WHERE id=$1 AND device_id=$2 FOR UPDATE`, commandID, deviceID).Scan(
		&r.ID, &r.ExecutionID, &r.Status, &r.AcknowledgedAt, &r.ResultCode,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, &AppError{404, "COMMAND_NOT_FOUND", "Komut bulunamadı."}
	}
	if err != nil {
		return nil, err
	}

	hash := resultHash(result, code, message)
	var existingKey, existingHash, existingStatus string
	var existingCode *string
	err = tx.QueryRow(ctx, `SELECT result_key, request_hash, status, code FROM command_results WHERE command_id=$1`, commandID).Scan(&existingKey, &existingHash, &existingStatus, &existingCode)
	if err == nil {
		if existingKey != key || existingHash != hash {
			return nil, &AppError{409, "IDEMPOTENCY_CONFLICT", "Komut sonucu daha önce farklı işlendi."}
		}
		return map[string]any{"id": fmt.Sprint(commandID), "status": existingStatus, "result_code": existingCode}, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return nil, err
	}
	if r.Status != "ACKNOWLEDGED" {
		return nil, &AppError{409, "COMMAND_NOT_RUNNING", "Komut çalışır durumda değil."}
	}
	now := time.Now().UTC()
	if r.AcknowledgedAt != nil && !r.AcknowledgedAt.After(now.Add(-120*time.Second)) {
		return nil, &AppError{409, "COMMAND_RESULT_EXPIRED", "Komut sonuç süresi doldu."}
	}
	payload, _ := json.Marshal(map[string]any{"result": result, "code": code, "message": message})
	if _, err := tx.Exec(ctx, `
INSERT INTO command_results (command_id,result_key,request_hash,status,code,message,payload,created_at)
VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)`, commandID, key, hash, result, code, message, string(payload), now); err != nil {
		return nil, err
	}
	if _, err := tx.Exec(ctx, `UPDATE commands SET status=$1, completed_at=$2, result_code=$3 WHERE id=$4`, result, now, code, commandID); err != nil {
		return nil, err
	}
	if _, err := tx.Exec(ctx, `UPDATE program_executions SET status=$1, completed_at=$2 WHERE id=$3`, result, now, r.ExecutionID); err != nil {
		return nil, err
	}
	eventPayload, _ := json.Marshal(map[string]any{"command_id": commandID, "status": result, "code": code})
	if _, err := tx.Exec(ctx, `INSERT INTO events (device_id,event_type,payload,created_at) VALUES ($1,'execution.completed',$2::jsonb,$3)`, deviceID, string(eventPayload), now); err != nil {
		return nil, err
	}
	return map[string]any{"id": fmt.Sprint(commandID), "status": result, "result_code": code}, nil
}
