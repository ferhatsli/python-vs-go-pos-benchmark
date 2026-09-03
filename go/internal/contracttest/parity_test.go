package contracttest

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"pos-backend-language-benchmark/go/internal/server"
	workerpkg "pos-backend-language-benchmark/go/internal/worker"
)

func databaseURL() string {
	if v := os.Getenv("BENCH_DATABASE_URL"); v != "" {
		return v
	}
	return "postgres://benchmark:benchmark-local-only@postgres:5432/pos_benchmark"
}

func newPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	cfg, err := pgxpool.ParseConfig(databaseURL())
	if err != nil {
		t.Fatal(err)
	}
	cfg.MaxConns = 40
	pool, err := pgxpool.NewWithConfig(context.Background(), cfg)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func exec(t *testing.T, pool *pgxpool.Pool, sql string) {
	t.Helper()
	for _, stmt := range strings.Split(sql, ";") {
		stmt = strings.TrimSpace(stmt)
		if stmt == "" {
			continue
		}
		if _, err := pool.Exec(context.Background(), stmt); err != nil {
			t.Fatalf("exec %q: %v", stmt, err)
		}
	}
}

func scalarInt(t *testing.T, pool *pgxpool.Pool, sql string) int64 {
	t.Helper()
	var v int64
	if err := pool.QueryRow(context.Background(), sql).Scan(&v); err != nil {
		t.Fatal(err)
	}
	return v
}

func scalarString(t *testing.T, pool *pgxpool.Pool, sql string) string {
	t.Helper()
	var v string
	if err := pool.QueryRow(context.Background(), sql).Scan(&v); err != nil {
		t.Fatal(err)
	}
	return v
}

func deviceHeaders(key string) http.Header {
	h := make(http.Header)
	h.Set("X-Device-Id", "1")
	h.Set("Authorization", "Device credential-1")
	if key != "" {
		h.Set("X-Idempotency-Key", key)
	}
	return h
}

func request(t *testing.T, client *http.Client, method, url string, headers http.Header, body any) (int, map[string]any) {
	t.Helper()
	var r io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatal(err)
		}
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, url, r)
	if err != nil {
		t.Fatal(err)
	}
	for k, values := range headers {
		for _, v := range values {
			req.Header.Add(k, v)
		}
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil {
		payload = map[string]any{"raw": string(raw)}
	}
	return resp.StatusCode, payload
}

func prepareDevice(t *testing.T, pool *pgxpool.Pool) {
	exec(t, pool, `
		UPDATE device_current_states SET last_seen_at=now(), current_configuration_version=1, acknowledged_configuration_version=1, updated_at=now() WHERE device_id=1;
		UPDATE devices SET status='ACTIVE' WHERE id=1;
		UPDATE wash_bays SET status='IDLE' WHERE device_id=1;
		DELETE FROM maintenance_windows WHERE device_id=1;
		UPDATE entitlements SET enabled=TRUE WHERE device_id=1 AND program_id=1;
		UPDATE program_payment_methods SET enabled=TRUE WHERE program_id=1;
		UPDATE program_executions SET status='SUCCESS', completed_at=now() WHERE wash_bay_id=1 AND status IN ('CREATED','COMMAND_SENT','RUNNING');
	`)
}

func TestHeartbeatAndConfigurationParity(t *testing.T) {
	pool := newPool(t)
	prepareDevice(t, pool)
	ts := httptest.NewServer(server.New(pool))
	defer ts.Close()
	client := ts.Client()

	bad := deviceHeaders("")
	bad.Set("Authorization", "Device wrong-token")
	status, payload := request(t, client, http.MethodPost, ts.URL+"/api/v1/device/heartbeat", bad, map[string]any{"sequence": 42, "app_version": "1.2.3", "state": map[string]any{"health": "OK"}})
	if status != 401 || payload["success"] != false {
		t.Fatalf("bad credential: status=%d payload=%v", status, payload)
	}

	before := scalarInt(t, pool, "SELECT count(*) FROM device_heartbeats WHERE device_id=1")
	status, payload = request(t, client, http.MethodPost, ts.URL+"/api/v1/device/heartbeat", deviceHeaders(""), map[string]any{"sequence": 4242, "app_version": "9.9.9", "state": map[string]any{"health": "OK", "signal": 88}})
	if status != 200 {
		t.Fatalf("heartbeat status=%d payload=%v", status, payload)
	}
	if scalarInt(t, pool, "SELECT count(*) FROM device_heartbeats WHERE device_id=1") != before+1 {
		t.Fatal("raw heartbeat not inserted")
	}
	if scalarString(t, pool, "SELECT app_version FROM device_current_states WHERE device_id=1") != "9.9.9" {
		t.Fatal("current state not updated")
	}

	status, payload = request(t, client, http.MethodGet, ts.URL+"/api/v1/device/configuration?current_version=1", deviceHeaders(""), nil)
	if status != 200 {
		t.Fatalf("configuration status=%d payload=%v", status, payload)
	}
	data := payload["data"].(map[string]any)
	if data["device_id"] != "dev-0000001" || data["station_id"] != "stn-000001" || data["update_available"] != false {
		t.Fatalf("configuration=%v", data)
	}
}

func TestCardIdempotencyAndFailureParity(t *testing.T) {
	pool := newPool(t)
	prepareDevice(t, pool)
	ts := httptest.NewServer(server.New(pool))
	defer ts.Close()
	client := ts.Client()
	exec(t, pool, "DELETE FROM payment_transactions WHERE idempotency_key LIKE 'go-card-%'")
	body := map[string]any{"station_program_id": 1, "payment_method": "CARD", "configuration_version": 1, "displayed_price_minor": 1000, "test_scenario": "TEST_SUCCESS"}
	s1, p1 := request(t, client, http.MethodPost, ts.URL+"/api/v1/device/payments", deviceHeaders("go-card-success"), body)
	s2, p2 := request(t, client, http.MethodPost, ts.URL+"/api/v1/device/payments", deviceHeaders("go-card-success"), body)
	if s1 != 200 || s2 != 200 {
		t.Fatalf("idempotency statuses %d %d payloads=%v %v", s1, s2, p1, p2)
	}
	id1 := p1["data"].(map[string]any)["id"]
	id2 := p2["data"].(map[string]any)["id"]
	if id1 != id2 {
		t.Fatalf("payment ids differ %v %v", id1, id2)
	}
	conflict := map[string]any{"station_program_id": 1, "payment_method": "CARD", "configuration_version": 1, "displayed_price_minor": 1500, "test_scenario": "TEST_SUCCESS"}
	s3, p3 := request(t, client, http.MethodPost, ts.URL+"/api/v1/device/payments", deviceHeaders("go-card-success"), conflict)
	if s3 != 409 || p3["error"].(map[string]any)["code"] != "IDEMPOTENCY_CONFLICT" {
		t.Fatalf("conflict %d %v", s3, p3)
	}

	failed := map[string]any{"station_program_id": 1, "payment_method": "CARD", "configuration_version": 1, "displayed_price_minor": 1000, "test_scenario": "TEST_FAILED"}
	s4, _ := request(t, client, http.MethodPost, ts.URL+"/api/v1/device/payments", deviceHeaders("go-card-failed"), failed)
	if s4 != 409 {
		t.Fatalf("failed status=%d", s4)
	}
	if scalarInt(t, pool, "SELECT count(*) FROM start_rights sr JOIN payment_transactions p ON p.id=sr.payment_id WHERE p.idempotency_key='go-card-failed'") != 0 {
		t.Fatal("failed card created start right")
	}
}

func TestQRAndRFContentionParity(t *testing.T) {
	pool := newPool(t)
	prepareDevice(t, pool)
	ts := httptest.NewServer(server.New(pool))
	defer ts.Close()
	client := ts.Client()

	exec(t, pool, "DELETE FROM payment_transactions WHERE idempotency_key LIKE 'go-qr-%'; UPDATE qr_codes SET usage_count=0,status='ACTIVE' WHERE id=1")
	qrBody := map[string]any{"payment_method": "QR", "configuration_version": 1, "qr_token": "qr-token-1"}
	var wg sync.WaitGroup
	statuses := make([]int, 2)
	for i, key := range []string{"go-qr-aa", "go-qr-bb"} {
		wg.Add(1)
		go func(i int, key string) {
			defer wg.Done()
			statuses[i], _ = request(t, client, http.MethodPost, ts.URL+"/api/v1/device/payments", deviceHeaders(key), qrBody)
		}(i, key)
	}
	wg.Wait()
	sort.Ints(statuses)
	if statuses[0] != 200 || statuses[1] != 409 {
		t.Fatalf("qr statuses=%v", statuses)
	}
	if scalarInt(t, pool, "SELECT usage_count FROM qr_codes WHERE id=1") != 1 {
		t.Fatal("qr usage != 1")
	}

	exec(t, pool, "DELETE FROM payment_transactions WHERE idempotency_key LIKE 'go-rf-%'; UPDATE rf_wallets SET balance_minor=1000,version=0,updated_at=now() WHERE id=1")
	rfBody := map[string]any{"station_program_id": 1, "payment_method": "RF_CARD", "configuration_version": 1, "displayed_price_minor": 1000, "rf_uid": "AABBCCDD00000001"}
	statuses = make([]int, 2)
	wg = sync.WaitGroup{}
	for i, key := range []string{"go-rf-aa", "go-rf-bb"} {
		wg.Add(1)
		go func(i int, key string) {
			defer wg.Done()
			statuses[i], _ = request(t, client, http.MethodPost, ts.URL+"/api/v1/device/payments", deviceHeaders(key), rfBody)
		}(i, key)
	}
	wg.Wait()
	sort.Ints(statuses)
	if statuses[0] != 200 || statuses[1] != 409 {
		t.Fatalf("rf statuses=%v", statuses)
	}
	if scalarInt(t, pool, "SELECT balance_minor FROM rf_wallets WHERE id=1") != 0 {
		t.Fatal("rf balance != 0")
	}
	if scalarInt(t, pool, "SELECT count(*) FROM rf_wallet_ledger l JOIN payment_transactions p ON p.id=l.payment_id WHERE p.idempotency_key LIKE 'go-rf-%' AND l.direction='DEBIT'") != 1 {
		t.Fatal("rf debit count != 1")
	}
}

func prepareCommand(t *testing.T, pool *pgxpool.Pool, id int) {
	exec(t, pool, `DELETE FROM command_results WHERE command_id=`+itoa(id)+`; UPDATE commands SET device_id=1,status='PENDING',sent_at=NULL,acknowledged_at=NULL,completed_at=NULL,result_code=NULL,created_at=now() WHERE id=`+itoa(id)+`; UPDATE program_executions SET device_id=1,wash_bay_id=1,status='CREATED',started_at=NULL,completed_at=NULL WHERE id=(SELECT program_execution_id FROM commands WHERE id=`+itoa(id)+`)`)
}

func itoa(v int) string {
	if v == 1 {
		return "1"
	}
	if v == 2 {
		return "2"
	}
	return "0"
}

func TestCommandLifecycleParity(t *testing.T) {
	pool := newPool(t)
	prepareCommand(t, pool, 1)
	ts := httptest.NewServer(server.New(pool))
	defer ts.Close()
	client := ts.Client()
	s, p := request(t, client, http.MethodGet, ts.URL+"/api/v1/device/commands/pending", deviceHeaders(""), nil)
	if s != 200 {
		t.Fatalf("pending=%d payload=%v", s, p)
	}
	s, p = request(t, client, http.MethodPost, ts.URL+"/api/v1/device/commands/1/acknowledge", deviceHeaders(""), nil)
	if s != 200 || p["data"].(map[string]any)["status"] != "ACKNOWLEDGED" {
		t.Fatalf("ack=%d %v", s, p)
	}
	resultBody := map[string]any{"result": "SUCCESS", "code": nil, "message": nil}
	s, p = request(t, client, http.MethodPost, ts.URL+"/api/v1/device/commands/1/result", deviceHeaders("go-command-result"), resultBody)
	if s != 200 || p["data"].(map[string]any)["status"] != "SUCCESS" {
		t.Fatalf("result=%d %v", s, p)
	}
	s, _ = request(t, client, http.MethodPost, ts.URL+"/api/v1/device/commands/1/result", deviceHeaders("go-command-result"), resultBody)
	if s != 200 {
		t.Fatalf("duplicate=%d", s)
	}
	s, p = request(t, client, http.MethodPost, ts.URL+"/api/v1/device/commands/1/result", deviceHeaders("go-command-result"), map[string]any{"result": "FAILED", "code": "HW", "message": "different"})
	if s != 409 || p["error"].(map[string]any)["code"] != "IDEMPOTENCY_CONFLICT" {
		t.Fatalf("conflict=%d %v", s, p)
	}
	if scalarInt(t, pool, "SELECT count(*) FROM command_results WHERE command_id=1") != 1 {
		t.Fatal("terminal result count != 1")
	}

	prepareCommand(t, pool, 2)
	s, _ = request(t, client, http.MethodGet, ts.URL+"/api/v1/device/commands/pending", deviceHeaders(""), nil)
	if s != 200 {
		t.Fatalf("pending2=%d", s)
	}
	s, p = request(t, client, http.MethodPost, ts.URL+"/api/v1/device/commands/2/result", deviceHeaders("go-command-early"), resultBody)
	if s != 409 || p["error"].(map[string]any)["code"] != "COMMAND_NOT_RUNNING" {
		t.Fatalf("early=%d %v", s, p)
	}
}

func TestDashboardScopeParity(t *testing.T) {
	pool := newPool(t)
	ts := httptest.NewServer(server.New(pool))
	defer ts.Close()
	client := ts.Client()
	bad := make(http.Header)
	bad.Set("Authorization", "Bearer wrong-token")
	s, _ := request(t, client, http.MethodGet, ts.URL+"/api/v1/dashboard/overview?period=TODAY", bad, nil)
	if s != 401 {
		t.Fatalf("bad panel auth=%d", s)
	}
	good := make(http.Header)
	good.Set("Authorization", "Bearer panel-company-1")
	s, p := request(t, client, http.MethodGet, ts.URL+"/api/v1/dashboard/overview?period=TODAY", good, nil)
	if s != 200 {
		t.Fatalf("dashboard=%d %v", s, p)
	}
	data := p["data"].(map[string]any)
	org := data["organization"].(map[string]any)
	if int(org["company_count"].(float64)) != 1 {
		t.Fatalf("organization=%v", org)
	}
}

func TestWorkerParityAndNPlusOneShape(t *testing.T) {
	pool := newPool(t)
	exec(t, pool, "DELETE FROM maintenance_windows; UPDATE device_current_states SET last_seen_at=now(),updated_at=now(); UPDATE device_current_states SET last_seen_at=now()-interval '10 minutes' WHERE device_id=1; DELETE FROM alarms WHERE alarm_key LIKE 'device%offline'; SELECT pg_stat_statements_reset()")
	result, err := workerpkg.Sweep(context.Background(), pool, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if result.AlarmsOpened != 1 {
		t.Fatalf("opened=%d", result.AlarmsOpened)
	}
	result, err = workerpkg.Sweep(context.Background(), pool, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if result.AlarmsOpened != 0 {
		t.Fatalf("dedupe opened=%d", result.AlarmsOpened)
	}
	calls := scalarInt(t, pool, "SELECT coalesce(sum(calls),0)::bigint FROM pg_stat_statements WHERE query LIKE '%FROM alarms%' AND query LIKE '%alarm_key%'")
	if calls < 500 {
		t.Fatalf("alarm lookup calls=%d want >=500", calls)
	}
	exec(t, pool, "UPDATE device_current_states SET last_seen_at=now(),updated_at=now() WHERE device_id=1")
	result, err = workerpkg.Sweep(context.Background(), pool, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	if result.AlarmsResolved < 1 {
		t.Fatalf("resolved=%d", result.AlarmsResolved)
	}
}
