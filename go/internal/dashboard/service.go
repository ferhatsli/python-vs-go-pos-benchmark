package dashboard

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type AppError struct {
	Status  int
	Code    string
	Message string
}

func (e *AppError) Error() string { return e.Code }

type Panel struct{ ID, CompanyID int64 }

func BearerToken(raw string) string {
	if !strings.HasPrefix(raw, "Bearer ") {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(raw, "Bearer "))
}

func Authenticate(ctx context.Context, pool *pgxpool.Pool, token string) (Panel, error) {
	h := sha256.Sum256([]byte(token))
	var p Panel
	err := pool.QueryRow(ctx, `SELECT id, company_id FROM panel_users WHERE token_hash=$1 AND active=TRUE`, hex.EncodeToString(h[:])).Scan(&p.ID, &p.CompanyID)
	if errors.Is(err, pgx.ErrNoRows) {
		return Panel{}, &AppError{401, "INVALID_PANEL_CREDENTIAL", "Panel kimliği doğrulanamadı."}
	}
	return p, err
}

func PeriodBounds(period string, now time.Time) (time.Time, time.Time, error) {
	now = now.UTC()
	today := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
	switch period {
	case "TODAY":
		return today, today.AddDate(0, 0, 1), nil
	case "LAST_7_DAYS":
		return today.AddDate(0, 0, -6), today.AddDate(0, 0, 1), nil
	case "THIS_MONTH":
		start := time.Date(today.Year(), today.Month(), 1, 0, 0, 0, 0, time.UTC)
		return start, start.AddDate(0, 1, 0), nil
	default:
		return time.Time{}, time.Time{}, &AppError{422, "INVALID_PERIOD", "Dashboard dönemi geçersiz."}
	}
}

func Overview(ctx context.Context, pool *pgxpool.Pool, companyID int64, period string) (map[string]any, error) {
	start, end, err := PeriodBounds(period, time.Now().UTC())
	if err != nil {
		return nil, err
	}
	var companyName string
	if err := pool.QueryRow(ctx, `SELECT name FROM companies WHERE id=$1`, companyID).Scan(&companyName); errors.Is(err, pgx.ErrNoRows) {
		return nil, &AppError{404, "COMPANY_NOT_FOUND", "Şirket bulunamadı."}
	} else if err != nil {
		return nil, err
	}

	var stationCount, bayCount int64
	if err := pool.QueryRow(ctx, `
SELECT
 (SELECT count(*) FROM stations WHERE company_id=$1),
 (SELECT count(*) FROM wash_bays wb JOIN stations s ON s.id=wb.station_id WHERE s.company_id=$1)`, companyID).Scan(&stationCount, &bayCount); err != nil {
		return nil, err
	}

	now := time.Now().UTC()
	var total, online, offline, unknown, active int64
	if err := pool.QueryRow(ctx, `
SELECT count(d.id),
 count(d.id) FILTER (WHERE cs.last_seen_at >= $2),
 count(d.id) FILTER (WHERE cs.last_seen_at < $2),
 count(d.id) FILTER (WHERE cs.last_seen_at IS NULL),
 count(d.id) FILTER (WHERE d.status='ACTIVE')
FROM devices d
JOIN stations s ON s.id=d.station_id
LEFT JOIN device_current_states cs ON cs.device_id=d.id
WHERE s.company_id=$1`, companyID, now.Add(-120*time.Second)).Scan(&total, &online, &offline, &unknown, &active); err != nil {
		return nil, err
	}

	var txCount, successCount, failedCount, pendingCount, cancelledCount, gross int64
	if err := pool.QueryRow(ctx, `
SELECT count(p.id),
 count(p.id) FILTER (WHERE p.status='SUCCESS'),
 count(p.id) FILTER (WHERE p.status='FAILED'),
 count(p.id) FILTER (WHERE p.status='PENDING'),
 count(p.id) FILTER (WHERE p.status='CANCELLED'),
 coalesce(sum(p.amount_minor) FILTER (WHERE p.status='SUCCESS'),0)::bigint
FROM payment_transactions p
JOIN stations s ON s.id=p.station_id
WHERE s.company_id=$1 AND p.created_at >= $2 AND p.created_at < $3`, companyID, start, end).Scan(&txCount, &successCount, &failedCount, &pendingCount, &cancelledCount, &gross); err != nil {
		return nil, err
	}

	rows, err := pool.Query(ctx, `
SELECT p.method, count(*)::bigint,
 count(*) FILTER (WHERE p.status='SUCCESS')::bigint,
 coalesce(sum(p.amount_minor) FILTER (WHERE p.status='SUCCESS'),0)::bigint
FROM payment_transactions p JOIN stations s ON s.id=p.station_id
WHERE s.company_id=$1 AND p.created_at >= $2 AND p.created_at < $3
GROUP BY p.method ORDER BY p.method`, companyID, start, end)
	if err != nil {
		return nil, err
	}
	methods := []map[string]any{}
	for rows.Next() {
		var method string
		var totalMethod, successfulMethod, amount int64
		if err := rows.Scan(&method, &totalMethod, &successfulMethod, &amount); err != nil {
			rows.Close()
			return nil, err
		}
		methods = append(methods, map[string]any{"payment_method": method, "count": successfulMethod, "amount": amount, "total_count": totalMethod, "successful_count": successfulMethod})
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()

	var failedExecutions int64
	if err := pool.QueryRow(ctx, `
SELECT count(e.id) FROM program_executions e
JOIN payment_transactions p ON p.id=e.payment_id
JOIN stations s ON s.id=p.station_id
WHERE s.company_id=$1 AND e.created_at >= $2 AND e.created_at < $3 AND e.status IN ('FAILED','TIMEOUT')`, companyID, start, end).Scan(&failedExecutions); err != nil {
		return nil, err
	}

	return map[string]any{
		"period":            period,
		"workspace_company": map[string]any{"id": formatID(companyID), "name": companyName},
		"period_start":      start.Format(time.RFC3339Nano), "period_end": end.Format(time.RFC3339Nano),
		"organization":           map[string]any{"dealer_count": int64(0), "company_count": int64(1), "station_count": stationCount, "wash_bay_count": bayCount},
		"devices":                map[string]any{"total": total, "online": online, "offline": offline, "unknown": unknown, "active": active, "suspended": int64(0)},
		"financial":              map[string]any{"transaction_count": txCount, "successful_transaction_count": successCount, "failed_transaction_count": failedCount, "pending_transaction_count": pendingCount, "cancelled_transaction_count": cancelledCount, "gross_amount": gross, "refund_amount": int64(0), "net_amount": gross, "currency": "TRY"},
		"payment_methods":        methods,
		"failed_execution_count": failedExecutions,
	}, nil
}

func formatID(v int64) string {
	const digits = "0123456789"
	if v == 0 {
		return "0"
	}
	var b [20]byte
	i := len(b)
	for v > 0 {
		i--
		b[i] = digits[v%10]
		v /= 10
	}
	return string(b[i:])
}
