import { check } from 'k6';

export const API_URL = __ENV.API_URL || 'http://127.0.0.1:48000';
export const DATASET_PROFILE = __ENV.DATASET_PROFILE || 'D1';
export const RUN_ID = __ENV.RUN_ID || 'local';
export const RUNTIME = __ENV.RUNTIME || 'unknown';
export const DRY_RUN = __ENV.DRY_RUN === '1';
export const ACCEPTANCE = __ENV.BENCH_ACCEPTANCE === '1';
export const ACCEPTANCE_DURATION = __ENV.BENCH_ACCEPTANCE_DURATION || '15s';
export const LOAD_LEVEL = Number(__ENV.BENCH_LOAD_LEVEL || 0);

const PROFILES = {
  D1: { devices: 500, stations: 50, companies: 10 },
  D2: { devices: 5000, stations: 500, companies: 50 },
  D3: { devices: 50000, stations: 5000, companies: 500 },
};

export function profile() {
  const value = PROFILES[DATASET_PROFILE];
  if (!value) {
    throw new Error(`unsupported DATASET_PROFILE=${DATASET_PROFILE}`);
  }
  return value;
}

export function deviceIdFor(vu = __VU, iter = __ITER, offset = 101) {
  const count = profile().devices;
  return ((offset - 1 + vu - 1 + iter) % count) + 1;
}

export function paymentDeviceIdFor(vu = __VU, iter = __ITER) {
  const firstFree = commandFixtureCount() + 1;
  const available = profile().devices - commandFixtureCount();
  return firstFree + ((vu - 1 + iter) % available);
}

export function deviceHeaders(deviceId, idempotencyKey = null) {
  const headers = {
    'Content-Type': 'application/json',
    'X-Device-Id': String(deviceId),
    Authorization: `Device credential-${deviceId}`,
  };
  if (idempotencyKey) headers['X-Idempotency-Key'] = idempotencyKey;
  return headers;
}

export function panelHeaders(companyId = 1) {
  return { Authorization: `Bearer panel-company-${companyId}` };
}

export function stationProgramId(deviceId) {
  const cfg = profile();
  const stationId = ((deviceId - 1) % cfg.stations) + 1;
  const companyId = ((stationId - 1) % cfg.companies) + 1;
  return ((companyId - 1) * 3) + 1;
}

export function uniqueKey(prefix, extra = '') {
  return `${RUN_ID}-${prefix}-${extra}-${__VU}-${__ITER}`.slice(0, 128);
}

export function contentionIndex() {
  const max = Math.max(100, Math.floor(profile().devices / 5));
  const requested = Number(__ENV.FIXTURE_INDEX || 1);
  return ((Math.max(requested, 1) - 1) % max) + 1;
}

export function commandFixtureCount() {
  return Math.max(10, Math.floor(profile().devices / 10));
}

export function contentionDeviceId() {
  return commandFixtureCount() + contentionIndex();
}

export function qrToken() {
  return `qr-token-${contentionIndex()}`;
}

export function rfUid() {
  return `AABBCCDD${contentionIndex().toString(16).toUpperCase().padStart(8, '0')}`;
}

export function checkJSON(response, label, allowedStatuses = [200]) {
  const ok = check(response, {
    [`${label}: status accepted`]: (r) => allowedStatuses.includes(r.status),
    [`${label}: json response`]: (r) => {
      try {
        r.json();
        return true;
      } catch (_) {
        return false;
      }
    },
  });
  return ok;
}

export function tags(workload) {
  return { workload, runtime: RUNTIME, dataset: DATASET_PROFILE, run_id: RUN_ID };
}
