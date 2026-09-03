package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"pos-backend-language-benchmark/go/internal/config"
	benchdb "pos-backend-language-benchmark/go/internal/db"
	"pos-backend-language-benchmark/go/internal/server"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "-healthcheck" {
		client := &http.Client{Timeout: 2 * time.Second}
		resp, err := client.Get("http://127.0.0.1:8000/health")
		if err != nil {
			log.Fatal(err)
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			log.Fatalf("health status=%d", resp.StatusCode)
		}
		return
	}

	cfg := config.Load()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	pool, err := benchdb.Open(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		log.Fatal(err)
	}

	httpServer := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           server.New(pool),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	fmt.Printf("go benchmark api listening on %s\n", cfg.HTTPAddr)
	if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
