import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { API_URL, DRY_RUN, contentionDeviceId, deviceHeaders, qrToken, tags, uniqueKey } from './common.js';

http.setResponseCallback(http.expectedStatuses(200, 409));
const qrSuccesses = new Counter('qr_successes');
const contentionVUs = DRY_RUN ? 2 : Number(__ENV.CONTENTION_VUS || 100);

export const options = {
  scenarios: {
    qr_contention: {
      executor: 'shared-iterations',
      vus: contentionVUs,
      iterations: contentionVUs,
      maxDuration: '30s',
    },
  },
  thresholds: {
    checks: ['rate==1'],
    qr_successes: ['count==1'],
  },
  tags: tags('payment-qr-contention'),
};

export default function () {
  const deviceId = contentionDeviceId();
  const body = {
    payment_method: 'QR',
    configuration_version: 1,
    qr_token: qrToken(),
  };
  const response = http.post(`${API_URL}/api/v1/device/payments`, JSON.stringify(body), {
    headers: deviceHeaders(deviceId, uniqueKey('qr-contention', String(__VU))),
    tags: { endpoint: 'payment-qr-contention' },
  });
  if (response.status === 200) qrSuccesses.add(1);
  check(response, {
    'qr contention status is success or consumed': (r) => r.status === 200 || r.status === 409,
    'qr contention rejection is QR_INVALID': (r) => r.status === 200 || r.json('error.code') === 'QR_INVALID',
  });
}
