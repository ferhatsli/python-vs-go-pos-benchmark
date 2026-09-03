package server

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"pos-backend-language-benchmark/go/internal/auth"
	"pos-backend-language-benchmark/go/internal/commands"
	"pos-backend-language-benchmark/go/internal/configuration"
	"pos-backend-language-benchmark/go/internal/dashboard"
	"pos-backend-language-benchmark/go/internal/heartbeat"
	"pos-backend-language-benchmark/go/internal/payments"
)

type Handler struct{ pool *pgxpool.Pool }

type heartbeatRequest struct {
	Sequence   *int64         `json:"sequence"`
	AppVersion *string        `json:"app_version"`
	State      map[string]any `json:"state"`
}

func New(pool *pgxpool.Pool) http.Handler {
	h := &Handler{pool: pool}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", h.health)
	mux.HandleFunc("POST /api/v1/device/heartbeat", h.heartbeat)
	mux.HandleFunc("GET /api/v1/device/configuration", h.configuration)
	mux.HandleFunc("POST /api/v1/device/payments", h.payment)
	mux.HandleFunc("GET /api/v1/device/commands/pending", h.commandsPending)
	mux.HandleFunc("POST /api/v1/device/commands/{command_id}/acknowledge", h.commandAcknowledge)
	mux.HandleFunc("POST /api/v1/device/commands/{command_id}/result", h.commandResult)
	mux.HandleFunc("GET /api/v1/dashboard/overview", h.dashboardOverview)
	return mux
}

func requestID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func meta() map[string]any {
	return map[string]any{"request_id": requestID(), "server_time": time.Now().UTC().Format(time.RFC3339Nano)}
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func success(w http.ResponseWriter, data any) {
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": data, "meta": meta()})
}
func fail(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]any{"success": false, "error": map[string]any{"code": code, "message": message, "details": map[string]any{}}, "meta": meta()})
}

func (h *Handler) withDeadline(r *http.Request) (context.Context, context.CancelFunc) {
	return context.WithTimeout(r.Context(), 5*time.Second)
}

func (h *Handler) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (h *Handler) authenticatedDeviceWith(r *http.Request, ctx context.Context, q auth.Querier) (auth.Device, bool) {
	rawID := strings.TrimSpace(r.Header.Get("X-Device-Id"))
	id, err := strconv.ParseInt(rawID, 10, 64)
	if err != nil {
		return auth.Device{}, false
	}
	d, err := auth.AuthenticateDevice(ctx, q, id, auth.Token(r.Header.Get("Authorization")))
	return d, err == nil
}

func (h *Handler) authenticatedDevice(r *http.Request, ctx context.Context) (auth.Device, bool) {
	return h.authenticatedDeviceWith(r, ctx, h.pool)
}

func (h *Handler) heartbeat(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := h.withDeadline(r)
	defer cancel()
	d, ok := h.authenticatedDevice(r, ctx)
	if !ok {
		fail(w, http.StatusUnauthorized, "INVALID_DEVICE_CREDENTIAL", "Cihaz kimliği doğrulanamadı.")
		return
	}
	var body heartbeatRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		fail(w, http.StatusUnprocessableEntity, "INVALID_REQUEST", "İstek geçersiz.")
		return
	}
	if body.State == nil {
		body.State = map[string]any{}
	}
	if err := heartbeat.Record(ctx, h.pool, d.ID, body.Sequence, body.AppVersion, body.State); err != nil {
		fail(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		return
	}
	success(w, map[string]any{"accepted": true, "next_heartbeat_seconds": 30})
}

func (h *Handler) configuration(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := h.withDeadline(r)
	defer cancel()
	d, ok := h.authenticatedDevice(r, ctx)
	if !ok {
		fail(w, http.StatusUnauthorized, "INVALID_DEVICE_CREDENTIAL", "Cihaz kimliği doğrulanamadı.")
		return
	}
	var current *int
	if raw := r.URL.Query().Get("current_version"); raw != "" {
		v, err := strconv.Atoi(raw)
		if err != nil || v < 1 {
			fail(w, http.StatusUnprocessableEntity, "INVALID_REQUEST", "İstek geçersiz.")
			return
		}
		current = &v
	}
	data, err := configuration.Get(ctx, h.pool, d.ID, current)
	if errors.Is(err, configuration.ErrNotFound) {
		fail(w, http.StatusNotFound, "CONFIGURATION_NOT_FOUND", "Cihaz yapılandırması bulunamadı.")
		return
	}
	if err != nil {
		fail(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		return
	}
	success(w, data)
}

func (h *Handler) payment(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := h.withDeadline(r)
	defer cancel()
	key := strings.TrimSpace(r.Header.Get("X-Idempotency-Key"))
	if len(key) < 8 || len(key) > 128 {
		fail(w, http.StatusUnprocessableEntity, "INVALID_IDEMPOTENCY_KEY", "Idempotency anahtarı geçersiz.")
		return
	}
	var body payments.Request
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.ConfigurationVersion < 1 {
		fail(w, http.StatusUnprocessableEntity, "INVALID_REQUEST", "İstek geçersiz.")
		return
	}

	tx, err := h.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		fail(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		return
	}
	defer tx.Rollback(ctx)
	d, ok := h.authenticatedDeviceWith(r, ctx, tx)
	if !ok {
		fail(w, http.StatusUnauthorized, "INVALID_DEVICE_CREDENTIAL", "Cihaz kimliği doğrulanamadı.")
		return
	}
	payload, err := payments.Create(ctx, tx, d, body, key)
	if err != nil {
		var appErr *payments.AppError
		if errors.As(err, &appErr) {
			fail(w, appErr.Status, appErr.Code, appErr.Message)
			return
		}
		fail(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		return
	}
	if err := tx.Commit(ctx); err != nil {
		fail(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error())
		return
	}
	status, _ := payload["status"].(string)
	if status == "FAILED" || status == "CANCELLED" {
		code, _ := payload["error_code"].(string)
		if code == "" {
			code = "PAYMENT_FAILED"
		}
		writeJSON(w, http.StatusConflict, map[string]any{"success": false, "error": map[string]any{"code": code, "message": code, "details": map[string]any{"payment_id": payload["id"], "status": status}}, "meta": meta()})
		return
	}
	if status == "PENDING" {
		writeJSON(w, http.StatusAccepted, map[string]any{"success": true, "data": payload, "meta": meta()})
		return
	}
	success(w, payload)
}

func commandIDFromPath(r *http.Request) (int64, bool) {
	id, err := strconv.ParseInt(r.PathValue("command_id"), 10, 64)
	return id, err == nil && id > 0
}

func (h *Handler) commandsPending(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := h.withDeadline(r)
	defer cancel()
	tx, err := h.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	defer tx.Rollback(ctx)
	d, ok := h.authenticatedDeviceWith(r, ctx, tx)
	if !ok {
		fail(w, 401, "INVALID_DEVICE_CREDENTIAL", "Cihaz kimliği doğrulanamadı.")
		return
	}
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		v, err := strconv.Atoi(raw)
		if err != nil || v < 1 || v > 100 {
			fail(w, 422, "INVALID_REQUEST", "İstek geçersiz.")
			return
		}
		limit = v
	}
	items, err := commands.Pending(ctx, tx, d.ID, limit)
	if err != nil {
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	if err := tx.Commit(ctx); err != nil {
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	success(w, map[string]any{"items": items, "next_poll_seconds": 5})
}

func (h *Handler) commandAcknowledge(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := h.withDeadline(r)
	defer cancel()
	commandID, ok := commandIDFromPath(r)
	if !ok {
		fail(w, 422, "INVALID_REQUEST", "İstek geçersiz.")
		return
	}
	tx, err := h.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	defer tx.Rollback(ctx)
	d, ok := h.authenticatedDeviceWith(r, ctx, tx)
	if !ok {
		fail(w, 401, "INVALID_DEVICE_CREDENTIAL", "Cihaz kimliği doğrulanamadı.")
		return
	}
	payload, err := commands.Acknowledge(ctx, tx, d.ID, commandID)
	if err != nil {
		var appErr *commands.AppError
		if errors.As(err, &appErr) {
			fail(w, appErr.Status, appErr.Code, appErr.Message)
			return
		}
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	if err := tx.Commit(ctx); err != nil {
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	success(w, payload)
}

type commandResultRequest struct {
	Result  string  `json:"result"`
	Code    *string `json:"code"`
	Message *string `json:"message"`
}

func (h *Handler) commandResult(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := h.withDeadline(r)
	defer cancel()
	commandID, ok := commandIDFromPath(r)
	if !ok {
		fail(w, 422, "INVALID_REQUEST", "İstek geçersiz.")
		return
	}
	key := strings.TrimSpace(r.Header.Get("X-Idempotency-Key"))
	if len(key) < 8 || len(key) > 128 {
		fail(w, 422, "INVALID_IDEMPOTENCY_KEY", "Idempotency anahtarı geçersiz.")
		return
	}
	var body commandResultRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		fail(w, 422, "INVALID_REQUEST", "İstek geçersiz.")
		return
	}
	tx, err := h.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	defer tx.Rollback(ctx)
	d, ok := h.authenticatedDeviceWith(r, ctx, tx)
	if !ok {
		fail(w, 401, "INVALID_DEVICE_CREDENTIAL", "Cihaz kimliği doğrulanamadı.")
		return
	}
	payload, err := commands.ApplyResult(ctx, tx, d.ID, commandID, body.Result, body.Code, body.Message, key)
	if err != nil {
		var appErr *commands.AppError
		if errors.As(err, &appErr) {
			fail(w, appErr.Status, appErr.Code, appErr.Message)
			return
		}
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	if err := tx.Commit(ctx); err != nil {
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	success(w, payload)
}

func (h *Handler) dashboardOverview(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := h.withDeadline(r)
	defer cancel()
	period := r.URL.Query().Get("period")
	if period == "" {
		period = "TODAY"
	}
	panel, err := dashboard.Authenticate(ctx, h.pool, dashboard.BearerToken(r.Header.Get("Authorization")))
	if err != nil {
		var appErr *dashboard.AppError
		if errors.As(err, &appErr) {
			fail(w, appErr.Status, appErr.Code, appErr.Message)
			return
		}
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	payload, err := dashboard.Overview(ctx, h.pool, panel.CompanyID, period)
	if err != nil {
		var appErr *dashboard.AppError
		if errors.As(err, &appErr) {
			fail(w, appErr.Status, appErr.Code, appErr.Message)
			return
		}
		fail(w, 500, "INTERNAL_ERROR", err.Error())
		return
	}
	success(w, payload)
}
