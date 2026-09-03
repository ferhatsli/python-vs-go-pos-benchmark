import http from 'k6/http';
import { check } from 'k6';
import { ACCEPTANCE, ACCEPTANCE_DURATION, API_URL, DRY_RUN, LOAD_LEVEL, deviceHeaders, paymentDeviceIdFor, stationProgramId, tags, uniqueKey } from './common.js';

const canonicalStages = [
  { target: 10, duration: '20s' },
  { target: 100, duration: '20s' },
  { target: 250, duration: '20s' },
  { target: 500, duration: '20s' },
  { target: 1000, duration: '20s' },
  { target: 2000, duration: '20s' },
];
const thresholds = { checks: ['rate==1'] };

const constantVUs = (name, vus, duration) => ({
  scenarios: { [name]: { executor: 'constant-vus', vus, duration } },
  thresholds,
  tags: tags('payment-card'),
});

export const options = DRY_RUN
  ? { vus: 1, iterations: 2, thresholds, tags: tags('payment-card') }
  : ACCEPTANCE
    ? constantVUs('card_acceptance', 10, ACCEPTANCE_DURATION)
    : LOAD_LEVEL > 0
      ? constantVUs('card_level', LOAD_LEVEL, __ENV.BENCH_LOAD_DURATION || '20s')
      : {
          scenarios: {
            card: { executor: 'ramping-vus', startVUs: 0, stages: canonicalStages, gracefulRampDown: '5s' },
          },
          thresholds,
          tags: tags('payment-card'),
        };

export default function () {
  const deviceId = paymentDeviceIdFor();
  const body = {
    station_program_id: stationProgramId(deviceId),
    payment_method: 'CARD',
    configuration_version: 1,
    displayed_price_minor: 1000,
    test_scenario: 'TEST_SUCCESS',
  };
  const key = uniqueKey('card', String(deviceId));
  const response = http.post(`${API_URL}/api/v1/device/payments`, JSON.stringify(body), {
    headers: deviceHeaders(deviceId, key),
    tags: { endpoint: 'payment-card' },
  });
  check(response, { 'card payment 200': (r) => r.status === 200 });
}
