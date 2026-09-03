package payments

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"

	"pos-backend-language-benchmark/go/internal/auth"
)

const (
	csrfSecret = "benchmark-csrf-secret"
	qrPepper   = "benchmark-qr-pepper"
)

type Request struct {
	StationProgramID     *int64  `json:"station_program_id"`
	PaymentMethod        string  `json:"payment_method"`
	ConfigurationVersion int     `json:"configuration_version"`
	DisplayedPriceMinor  *int64  `json:"displayed_price_minor"`
	QRToken              *string `json:"qr_token"`
	RFUID                *string `json:"rf_uid"`
	TestScenario         *string `json:"test_scenario"`
}

type AppError struct {
	Status  int
	Code    string
	Message string
	Details map[string]any
}

func (e *AppError) Error() string { return e.Code }

func appErr(status int, code, message string) *AppError {
	return &AppError{Status: status, Code: code, Message: message, Details: map[string]any{}}
}

func secretHash(value, pepper string) string {
	m := hmac.New(sha256.New, []byte(pepper))
	_, _ = m.Write([]byte(value))
	return hex.EncodeToString(m.Sum(nil))
}

func requestHash(req Request) (string, error) {
	b, err := json.Marshal(req)
	if err != nil {
		return "", err
	}
	return secretHash(string(b), csrfSecret), nil
}

var nonHex = regexp.MustCompile(`[^0-9A-Fa-f]`)

func normalizeUID(value string) (string, *AppError) {
	n := strings.ToUpper(nonHex.ReplaceAllString(value, ""))
	if len(n) < 8 || len(n) > 64 || len(n)%2 != 0 {
		return "", appErr(422, "INVALID_RF_UID", "RF UID biçimi geçersiz.")
	}
	return n, nil
}

func paymentPayload(ctx context.Context, q interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}, paymentID int64) (map[string]any, error) {
	var id int64
	var status, method, currency string
	var amount int64
	var errorCode pgtype.Text
	var createdAt time.Time
	var programID pgtype.Int8
	if err := q.QueryRow(ctx, `
		SELECT id,status,method,amount_minor,currency,error_code,created_at,program_id
		FROM payment_transactions WHERE id=$1
	`, paymentID).Scan(&id, &status, &method, &amount, &currency, &errorCode, &createdAt, &programID); err != nil {
		return nil, err
	}
	var rightID int64
	var rightStatus string
	rightErr := q.QueryRow(ctx, `SELECT id,status FROM start_rights WHERE payment_id=$1`, paymentID).Scan(&rightID, &rightStatus)
	var execID int64
	var execStatus string
	execErr := q.QueryRow(ctx, `SELECT id,status FROM program_executions WHERE payment_id=$1`, paymentID).Scan(&execID, &execStatus)
	var errorValue any
	if errorCode.Valid {
		errorValue = errorCode.String
	}
	var programValue any
	if programID.Valid {
		programValue = fmt.Sprintf("%d", programID.Int64)
	}
	payload := map[string]any{
		"id":                 fmt.Sprintf("%d", id),
		"code":               fmt.Sprintf("PAY-%012d", id),
		"status":             status,
		"payment_method":     method,
		"amount_minor":       amount,
		"currency":           currency,
		"error_code":         errorValue,
		"station_program_id": programValue,
		"created_at":         createdAt.Format(time.RFC3339Nano),
		"start_right":        nil,
		"execution":          nil,
	}
	if rightErr == nil {
		payload["start_right"] = map[string]any{"id": fmt.Sprintf("%d", rightID), "status": rightStatus}
	}
	if execErr == nil {
		payload["execution"] = map[string]any{"id": fmt.Sprintf("%d", execID), "status": execStatus}
	}
	return payload, nil
}

func Create(ctx context.Context, tx pgx.Tx, device auth.Device, req Request, key string) (map[string]any, error) {
	deviceID := device.ID
	stationID := device.StationID
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, fmt.Sprintf("payment:%d:%s", deviceID, key)); err != nil {
		return nil, err
	}

	bodyHash, err := requestHash(req)
	if err != nil {
		return nil, err
	}
	var existingID int64
	var existingHash string
	err = tx.QueryRow(ctx, `SELECT id,request_hash FROM payment_transactions WHERE device_id=$1 AND idempotency_key=$2`, deviceID, key).Scan(&existingID, &existingHash)
	if err == nil {
		if existingHash != bodyHash {
			return nil, appErr(409, "IDEMPOTENCY_CONFLICT", "Aynı anahtar farklı bir ödeme isteğinde kullanıldı.")
		}
		return paymentPayload(ctx, tx, existingID)
	}
	if err != pgx.ErrNoRows {
		return nil, err
	}

	now := time.Now().UTC()
	if device.Status != "ACTIVE" {
		return nil, appErr(409, "DEVICE_NOT_OPERATIONAL", "Cihaz işlem için aktif değil.")
	}
	var companyID int64
	if err := tx.QueryRow(ctx, `SELECT company_id FROM stations WHERE id=$1`, stationID).Scan(&companyID); err != nil {
		return nil, appErr(409, "DEVICE_NOT_OPERATIONAL", "Cihaz istasyonu bulunamadı.")
	}

	var lastSeen pgtype.Timestamptz
	var ackVersion pgtype.Int4
	if err := tx.QueryRow(ctx, `SELECT last_seen_at,acknowledged_configuration_version FROM device_current_states WHERE device_id=$1`, deviceID).Scan(&lastSeen, &ackVersion); err != nil || !lastSeen.Valid || lastSeen.Time.Before(now.Add(-120*time.Second)) {
		return nil, appErr(409, "DEVICE_OFFLINE", "Çevrimdışı cihazda ödeme başlatılamaz.")
	}
	var washBayID int64
	var washBayStatus string
	if err := tx.QueryRow(ctx, `SELECT id,status FROM wash_bays WHERE device_id=$1`, deviceID).Scan(&washBayID, &washBayStatus); err != nil {
		return nil, appErr(409, "DEVICE_NOT_ASSIGNED", "Cihaz bir perona bağlı değil.")
	}
	var maintenanceID int64
	err = tx.QueryRow(ctx, `SELECT id FROM maintenance_windows WHERE device_id=$1 AND status='ACTIVE' AND starts_at <= $2 AND ends_at > $2 LIMIT 1`, deviceID, now).Scan(&maintenanceID)
	if err == nil {
		return nil, appErr(409, "DEVICE_IN_MAINTENANCE", "Bakım durumundaki cihazda yeni ödeme başlatılamaz.")
	}
	if err != pgx.ErrNoRows {
		return nil, err
	}
	var publishedVersion int
	if err := tx.QueryRow(ctx, `SELECT version FROM device_configurations WHERE device_id=$1 AND status='PUBLISHED'`, deviceID).Scan(&publishedVersion); err != nil || publishedVersion != req.ConfigurationVersion || !ackVersion.Valid || int(ackVersion.Int32) != publishedVersion {
		return nil, appErr(409, "CONFIGURATION_NOT_ACKNOWLEDGED", "Güncel cihaz yapılandırması uygulanmadan ödeme başlatılamaz.")
	}
	var busyID int64
	err = tx.QueryRow(ctx, `SELECT id FROM program_executions WHERE wash_bay_id=$1 AND status IN ('CREATED','COMMAND_SENT','RUNNING') LIMIT 1`, washBayID).Scan(&busyID)
	if err == nil {
		return nil, appErr(409, "WASH_BAY_BUSY", "Peronda devam eden bir program bulunuyor.")
	}
	if err != pgx.ErrNoRows {
		return nil, err
	}

	method := req.PaymentMethod
	var programID int64
	if method == "QR" {
		if req.QRToken == nil {
			return nil, appErr(422, "QR_TOKEN_REQUIRED", "QR token zorunludur.")
		}
		tokenHash := secretHash(*req.QRToken, qrPepper)
		var qCompany, qStation int64
		if err := tx.QueryRow(ctx, `SELECT company_id,station_id,program_id FROM qr_codes WHERE token_hash=$1`, tokenHash).Scan(&qCompany, &qStation, &programID); err != nil || qCompany != companyID || qStation != stationID {
			return nil, appErr(404, "QR_NOT_FOUND", "QR kod bu istasyonda geçerli değil.")
		}
	} else {
		if req.StationProgramID == nil {
			return nil, appErr(422, "STATION_PROGRAM_REQUIRED", "Program zorunludur.")
		}
		programID = *req.StationProgramID
	}
	var programPrice int64
	if err := tx.QueryRow(ctx, `SELECT price_minor FROM programs WHERE id=$1 AND company_id=$2 AND active=TRUE`, programID, companyID).Scan(&programPrice); err != nil {
		return nil, appErr(409, "PROGRAM_NOT_AVAILABLE", "Program kullanılamıyor.")
	}
	var entitlementID int64
	if err := tx.QueryRow(ctx, `SELECT id FROM entitlements WHERE device_id=$1 AND program_id=$2 AND enabled=TRUE`, deviceID, programID).Scan(&entitlementID); err != nil {
		return nil, appErr(409, "ENTITLEMENT_REQUIRED", "Cihaz program yetkisine sahip değil.")
	}
	var methodID int64
	if err := tx.QueryRow(ctx, `SELECT id FROM program_payment_methods WHERE program_id=$1 AND payment_method=$2 AND enabled=TRUE`, programID, method).Scan(&methodID); err != nil {
		return nil, appErr(409, "PAYMENT_METHOD_NOT_AVAILABLE", "Ödeme yöntemi bu programda açık değil.")
	}
	if method == "CARD" || method == "RF_CARD" {
		if req.DisplayedPriceMinor == nil || *req.DisplayedPriceMinor != programPrice {
			e := appErr(409, "PROGRAM_PRICE_CHANGED", "Program fiyatı değişti. Güncel fiyatı onaylayıp tekrar deneyin.")
			e.Details["current_price_minor"] = programPrice
			return nil, e
		}
	}

	status := "SUCCESS"
	var errorCode *string
	amountMinor := programPrice
	var qrCodeID *int64
	var rfWalletID *int64

	switch method {
	case "CARD":
		scenario := ""
		if req.TestScenario != nil {
			scenario = *req.TestScenario
		}
		switch scenario {
		case "TEST_SUCCESS":
			status = "SUCCESS"
		case "TEST_FAILED":
			v := "CARD_DECLINED"
			status = "FAILED"
			errorCode = &v
		case "TEST_CANCELLED":
			v := "CARD_CANCELLED"
			status = "CANCELLED"
			errorCode = &v
		case "TEST_TIMEOUT":
			status = "PENDING"
		case "TEST_INSUFFICIENT_FUNDS":
			v := "INSUFFICIENT_FUNDS"
			status = "FAILED"
			errorCode = &v
		case "TEST_PROVIDER_ERROR":
			v := "PROVIDER_ERROR"
			status = "FAILED"
			errorCode = &v
		default:
			return nil, appErr(422, "INVALID_TEST_SCENARIO", "Kart test senaryosu geçersiz.")
		}
	case "QR":
		tokenHash := secretHash(*req.QRToken, qrPepper)
		var id, qCompany, qStation, qProgram, qAmount int64
		var currency string
		var usageLimit, usageCount int
		var qStatus string
		var startsAt, expiresAt time.Time
		err := tx.QueryRow(ctx, `
			SELECT id,company_id,station_id,program_id,amount_minor,currency,usage_limit,usage_count,status,starts_at,expires_at
			FROM qr_codes WHERE token_hash=$1 FOR UPDATE
		`, tokenHash).Scan(&id, &qCompany, &qStation, &qProgram, &qAmount, &currency, &usageLimit, &usageCount, &qStatus, &startsAt, &expiresAt)
		if err != nil || qStatus != "ACTIVE" || qCompany != companyID || qStation != stationID || qProgram != programID || startsAt.After(now) || !expiresAt.After(now) || usageCount >= usageLimit {
			v := "QR_INVALID"
			status = "FAILED"
			errorCode = &v
		} else {
			qrCodeID = &id
			amountMinor = qAmount
			usageCount++
			newStatus := "ACTIVE"
			if usageCount >= usageLimit {
				newStatus = "USED"
			}
			if _, err := tx.Exec(ctx, `UPDATE qr_codes SET usage_count=$1,status=$2 WHERE id=$3`, usageCount, newStatus, id); err != nil {
				return nil, err
			}
		}
	case "RF_CARD":
		if req.RFUID == nil {
			return nil, appErr(422, "INVALID_RF_UID", "RF UID biçimi geçersiz.")
		}
		uid, e := normalizeUID(*req.RFUID)
		if e != nil {
			return nil, e
		}
		uidHash := secretHash(uid, qrPepper)
		var cardID, cardCompany int64
		var cardStatus string
		var expires pgtype.Timestamptz
		err := tx.QueryRow(ctx, `SELECT id,company_id,status,expires_at FROM rf_cards WHERE uid_hash=$1`, uidHash).Scan(&cardID, &cardCompany, &cardStatus, &expires)
		if err != nil || cardStatus != "ACTIVE" || cardCompany != companyID || (expires.Valid && !expires.Time.After(now)) {
			v := "RF_CARD_INVALID"
			status = "FAILED"
			errorCode = &v
		} else {
			var walletID, balance, version int64
			err = tx.QueryRow(ctx, `SELECT id,balance_minor,version FROM rf_wallets WHERE rf_card_id=$1 FOR UPDATE`, cardID).Scan(&walletID, &balance, &version)
			if err != nil || balance < programPrice {
				v := "RF_INSUFFICIENT_BALANCE"
				status = "FAILED"
				errorCode = &v
			} else {
				rfWalletID = &walletID
				if _, err := tx.Exec(ctx, `UPDATE rf_wallets SET balance_minor=balance_minor-$1,version=version+1,updated_at=$2 WHERE id=$3`, programPrice, now, walletID); err != nil {
					return nil, err
				}
			}
		}
	default:
		return nil, appErr(422, "UNSUPPORTED_PAYMENT_METHOD", "Ödeme yöntemi desteklenmiyor.")
	}

	var completedAt *time.Time
	if status != "PENDING" {
		completedAt = &now
	}
	var paymentID int64
	if err := tx.QueryRow(ctx, `
		INSERT INTO payment_transactions (
			device_id,station_id,idempotency_key,request_hash,method,amount_minor,currency,status,error_code,error_message,program_id,qr_code_id,rf_wallet_id,created_at,completed_at
		) VALUES ($1,$2,$3,$4,$5,$6,'TRY',$7,$8,$8,$9,$10,$11,$12,$13)
		RETURNING id
	`, deviceID, stationID, key, bodyHash, method, amountMinor, status, errorCode, programID, qrCodeID, rfWalletID, now, completedAt).Scan(&paymentID); err != nil {
		return nil, err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO payment_attempts (payment_id,attempt_no,status,created_at) VALUES ($1,1,$2,$3)`, paymentID, status, now); err != nil {
		return nil, err
	}
	if method == "CARD" {
		if _, err := tx.Exec(ctx, `INSERT INTO provider_transactions (payment_id,provider_ref,status,created_at) VALUES ($1,$2,$3,$4)`, paymentID, fmt.Sprintf("MOCK-%d", paymentID), status, now); err != nil {
			return nil, err
		}
	}
	if method == "RF_CARD" && status == "SUCCESS" && rfWalletID != nil {
		if _, err := tx.Exec(ctx, `INSERT INTO rf_wallet_ledger (wallet_id,payment_id,direction,amount_minor,created_at) VALUES ($1,$2,'DEBIT',$3,$4)`, *rfWalletID, paymentID, programPrice, now); err != nil {
			return nil, err
		}
	}
	if status == "SUCCESS" {
		if _, err := tx.Exec(ctx, `INSERT INTO start_rights (payment_id,device_id,wash_bay_id,program_id,status,created_at) VALUES ($1,$2,$3,$4,'AVAILABLE',$5)`, paymentID, deviceID, washBayID, programID, now); err != nil {
			return nil, err
		}
	}
	eventPayload, _ := json.Marshal(map[string]any{"status": status, "method": method, "error_code": errorCode})
	if _, err := tx.Exec(ctx, `INSERT INTO events (device_id,payment_id,event_type,payload,created_at) VALUES ($1,$2,'payment.completed',$3::jsonb,$4)`, deviceID, paymentID, eventPayload, now); err != nil {
		return nil, err
	}
	auditPayload, _ := json.Marshal(map[string]any{"status": status})
	if _, err := tx.Exec(ctx, `INSERT INTO audit_entries (payment_id,action,payload,created_at) VALUES ($1,'payment.completed',$2::jsonb,$3)`, paymentID, auditPayload, now); err != nil {
		return nil, err
	}
	return paymentPayload(ctx, tx, paymentID)
}
