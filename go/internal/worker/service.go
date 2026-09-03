package worker

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Result struct {
	AlarmsOpened         int
	AlarmsResolved       int
	MaintenanceActivated int
	MaintenanceCompleted int
	DevicesEvaluated     int
}

type deviceRow struct {
	ID       int64
	LastSeen *time.Time
}

func Sweep(ctx context.Context, pool *pgxpool.Pool, now time.Time) (Result, error) {
	now = now.UTC()
	tx, err := pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return Result{}, err
	}
	defer tx.Rollback(ctx)

	activatedTag, err := tx.Exec(ctx, `
UPDATE maintenance_windows SET status='ACTIVE'
WHERE status='SCHEDULED' AND starts_at <= $1 AND ends_at > $1`, now)
	if err != nil {
		return Result{}, err
	}
	completedTag, err := tx.Exec(ctx, `
UPDATE maintenance_windows SET status='COMPLETED'
WHERE status IN ('SCHEDULED','ACTIVE') AND ends_at <= $1`, now)
	if err != nil {
		return Result{}, err
	}

	maintenanceRows, err := tx.Query(ctx, `
SELECT device_id FROM maintenance_windows
WHERE status='ACTIVE' AND starts_at <= $1 AND ends_at > $1 AND device_id IS NOT NULL`, now)
	if err != nil {
		return Result{}, err
	}
	activeMaintenance := map[int64]struct{}{}
	for maintenanceRows.Next() {
		var id int64
		if err := maintenanceRows.Scan(&id); err != nil {
			maintenanceRows.Close()
			return Result{}, err
		}
		activeMaintenance[id] = struct{}{}
	}
	if err := maintenanceRows.Err(); err != nil {
		maintenanceRows.Close()
		return Result{}, err
	}
	maintenanceRows.Close()

	rows, err := tx.Query(ctx, `
SELECT d.id, cs.last_seen_at
FROM devices d
LEFT JOIN device_current_states cs ON cs.device_id=d.id
WHERE d.status='ACTIVE'
ORDER BY d.id`)
	if err != nil {
		return Result{}, err
	}
	devices := make([]deviceRow, 0, 512)
	for rows.Next() {
		var r deviceRow
		if err := rows.Scan(&r.ID, &r.LastSeen); err != nil {
			rows.Close()
			return Result{}, err
		}
		devices = append(devices, r)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return Result{}, err
	}
	rows.Close()

	opened := 0
	resolved := 0
	for _, r := range devices {
		alarmKey := fmt.Sprintf("device:%d:offline", r.ID)
		var existingID *int64
		var id int64
		err := tx.QueryRow(ctx, `
SELECT id FROM alarms
WHERE device_id=$1 AND alarm_key=$2 AND status='OPEN'
LIMIT 1`, r.ID, alarmKey).Scan(&id)
		if err == nil {
			existingID = &id
		} else if err != pgx.ErrNoRows {
			return Result{}, err
		}

		isOffline := r.LastSeen != nil && r.LastSeen.Before(now.Add(-120*time.Second))
		isAlarmDue := r.LastSeen != nil && r.LastSeen.Before(now.Add(-5*time.Minute))
		_, inMaintenance := activeMaintenance[r.ID]
		if isAlarmDue && !inMaintenance {
			if existingID == nil {
				if _, err := tx.Exec(ctx, `INSERT INTO alarms (device_id,alarm_key,status,opened_at) VALUES ($1,$2,'OPEN',$3)`, r.ID, alarmKey, now); err != nil {
					return Result{}, err
				}
				opened++
			}
		} else if !isOffline && existingID != nil {
			if _, err := tx.Exec(ctx, `UPDATE alarms SET status='RESOLVED', closed_at=$1 WHERE id=$2 AND status='OPEN'`, now, *existingID); err != nil {
				return Result{}, err
			}
			resolved++
		}
	}

	failureRows, err := tx.Query(ctx, `
SELECT device_id, count(*)
FROM program_executions
WHERE created_at >= $1 AND status IN ('FAILED','TIMEOUT')
GROUP BY device_id
HAVING count(*) >= 3`, now.Add(-10*time.Minute))
	if err != nil {
		return Result{}, err
	}
	type failureRow struct{ DeviceID, Count int64 }
	var failures []failureRow
	for failureRows.Next() {
		var r failureRow
		if err := failureRows.Scan(&r.DeviceID, &r.Count); err != nil {
			failureRows.Close()
			return Result{}, err
		}
		failures = append(failures, r)
	}
	if err := failureRows.Err(); err != nil {
		failureRows.Close()
		return Result{}, err
	}
	failureRows.Close()

	for _, r := range failures {
		alarmKey := fmt.Sprintf("device:%d:execution-failures", r.DeviceID)
		var existing int64
		err := tx.QueryRow(ctx, `
SELECT id FROM alarms
WHERE device_id=$1 AND alarm_key=$2 AND status='OPEN'
LIMIT 1`, r.DeviceID, alarmKey).Scan(&existing)
		if err == pgx.ErrNoRows {
			if _, err := tx.Exec(ctx, `INSERT INTO alarms (device_id,alarm_key,status,opened_at) VALUES ($1,$2,'OPEN',$3)`, r.DeviceID, alarmKey, now); err != nil {
				return Result{}, err
			}
			opened++
		} else if err != nil {
			return Result{}, err
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return Result{}, err
	}
	return Result{
		AlarmsOpened:         opened,
		AlarmsResolved:       resolved,
		MaintenanceActivated: int(activatedTag.RowsAffected()),
		MaintenanceCompleted: int(completedTag.RowsAffected()),
		DevicesEvaluated:     len(devices),
	}, nil
}
