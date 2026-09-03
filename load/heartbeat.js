import http from 'k6/http';
import { check } from 'k6';
import { ACCEPTANCE, ACCEPTANCE_DURATION, API_URL, DRY_RUN, LOAD_LEVEL, deviceHeaders, deviceIdFor, tags } from './common.js';

const canonicalStages = [
  { target: 17, duration: '30s' },
  { target: 167, duration: '30s' },
  { target: 1667, duration: '30s' },
  { target: 3333, duration: '30s' },
];
const thresholds = { checks: ['rate==1'] };

const constantArrival = (name, rate, duration) => ({
  scenarios: {
    [name]: {
      executor: 'constant-arrival-rate',
      rate,
      timeUnit: '1s',
      duration,
      preAllocatedVUs: 500,
      maxVUs: 5000,
    },
  },
  thresholds,
  tags: tags('heartbeat'),
});

export const options = DRY_RUN
  ? { vus: 1, iterations: 2, thresholds, tags: tags('heartbeat') }
  : ACCEPTANCE
    ? constantArrival('heartbeat_acceptance', 17, ACCEPTANCE_DURATION)
    : LOAD_LEVEL > 0
      ? constantArrival('heartbeat_level', LOAD_LEVEL, __ENV.BENCH_LOAD_DURATION || '30s')
      : {
          scenarios: {
            heartbeat: {
              executor: 'ramping-arrival-rate',
              startRate: 17,
              timeUnit: '1s',
              preAllocatedVUs: 500,
              maxVUs: 5000,
              stages: canonicalStages,
            },
          },
          thresholds,
          tags: tags('heartbeat'),
        };

export default function () {
  const deviceId = deviceIdFor();
  const response = http.post(
    `${API_URL}/api/v1/device/heartbeat`,
    JSON.stringify({ sequence: __ITER + 1, app_version: 'k6', state: { run: 'heartbeat' } }),
    { headers: deviceHeaders(deviceId), tags: { endpoint: 'heartbeat' } },
  );
  check(response, { 'heartbeat 200': (r) => r.status === 200 });
}
