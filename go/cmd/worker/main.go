package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"time"

	"pos-backend-language-benchmark/go/internal/config"
	benchdb "pos-backend-language-benchmark/go/internal/db"
	"pos-backend-language-benchmark/go/internal/worker"
)

func main() {
	cfg := config.Load()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	pool, err := benchdb.Open(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer pool.Close()

	started := time.Now()
	result, err := worker.Sweep(ctx, pool, time.Now().UTC())
	if err != nil {
		log.Fatal(err)
	}
	durationMS := float64(time.Since(started).Nanoseconds()) / 1_000_000.0
	devicesPerSecond := 0.0
	if durationMS > 0 {
		devicesPerSecond = float64(result.DevicesEvaluated) / (durationMS / 1000.0)
	}
	payload := map[string]any{
		"devices_evaluated":      result.DevicesEvaluated,
		"alarms_opened":          result.AlarmsOpened,
		"alarms_resolved":        result.AlarmsResolved,
		"maintenance_activated":  result.MaintenanceActivated,
		"maintenance_completed":  result.MaintenanceCompleted,
		"duration_ms":            durationMS,
		"devices_per_second":     devicesPerSecond,
		"overrun_5s":             durationMS > 5000.0,
	}
	if err := json.NewEncoder(os.Stdout).Encode(payload); err != nil {
		log.Fatal(err)
	}
}
