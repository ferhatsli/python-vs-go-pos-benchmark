package config

import "os"

type Config struct {
	DatabaseURL string
	HTTPAddr    string
}

func Load() Config {
	db := os.Getenv("BENCH_DATABASE_URL")
	if db == "" {
		db = "postgres://benchmark:benchmark-local-only@postgres:5432/pos_benchmark"
	}
	addr := os.Getenv("BENCH_HTTP_ADDR")
	if addr == "" {
		addr = "0.0.0.0:8000"
	}
	return Config{DatabaseURL: db, HTTPAddr: addr}
}
