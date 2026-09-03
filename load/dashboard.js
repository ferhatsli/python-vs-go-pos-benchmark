import http from 'k6/http';
import { check } from 'k6';
import { ACCEPTANCE, ACCEPTANCE_DURATION, API_URL, DRY_RUN, LOAD_LEVEL, panelHeaders, tags } from './common.js';

const canonicalStages = [
  { target: 10, duration: '20s' },
  { target: 50, duration: '20s' },
  { target: 100, duration: '20s' },
  { target: 200, duration: '20s' },
];
const thresholds = { checks: ['rate==1'] };

const constantVUs = (name, vus, duration) => ({
  scenarios: { [name]: { executor: 'constant-vus', vus, duration } },
  thresholds,
  tags: tags('dashboard'),
});

export const options = DRY_RUN
  ? { vus: 1, iterations: 2, thresholds, tags: tags('dashboard') }
  : ACCEPTANCE
    ? constantVUs('dashboard_acceptance', 10, ACCEPTANCE_DURATION)
    : LOAD_LEVEL > 0
      ? constantVUs('dashboard_level', LOAD_LEVEL, __ENV.BENCH_LOAD_DURATION || '20s')
      : {
          scenarios: {
            dashboard: { executor: 'ramping-vus', startVUs: 0, stages: canonicalStages, gracefulRampDown: '5s' },
          },
          thresholds,
          tags: tags('dashboard'),
        };

export default function () {
  const response = http.get(`${API_URL}/api/v1/dashboard/overview?period=TODAY`, {
    headers: panelHeaders(1),
    tags: { endpoint: 'dashboard-overview' },
  });
  check(response, { 'dashboard 200': (r) => r.status === 200 });
}
