import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { API_URL, DRY_RUN, contentionDeviceId, deviceHeaders, rfUid, stationProgramId, tags, uniqueKey } from './common.js';

http.setResponseCallback(http.expectedStatuses(200, 409));
const rfSuccesses = new Counter('rf_successes');
const contentionVUs = DRY_RUN ? 2 : Number(__ENV.CONTENTION_VUS || 100);

export const options = {
  scenarios: {
    rf_contention: {
      executor: 'shared-iterations',
      vus: contentionVUs,
      iterations: contentionVUs,
      maxDuration: '30s',
    },
  },
  thresholds: {
    checks: ['rate==1'],
    rf_successes: ['count==1'],
  },
  tags: tags('payment-rf-contention'),
};

export default function () {
  const deviceId = contentionDeviceId();
  const body = {
    station_program_id: stationProgramId(deviceId),
    payment_method: 'RF_CARD',
    configuration_version: 1,
    displayed_price_minor: 1000,
    rf_uid: rfUid(),
  };
  const response = http.post(`${API_URL}/api/v1/device/payments`, JSON.stringify(body), {
    headers: deviceHeaders(deviceId, uniqueKey('rf-contention', String(__VU))),
    tags: { endpoint: 'payment-rf-contention' },
  });
  if (response.status === 200) rfSuccesses.add(1);
  check(response, {
    'rf contention status is success or insufficient': (r) => r.status === 200 || r.status === 409,
    'rf contention rejection is insufficient balance': (r) => r.status === 200 || r.json('error.code') === 'RF_INSUFFICIENT_BALANCE',
  });
}
