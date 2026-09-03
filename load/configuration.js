import http from 'k6/http';
import { check } from 'k6';
import { API_URL, DRY_RUN, deviceHeaders, deviceIdFor, tags } from './common.js';

const thresholds = { checks: ['rate==1'] };

export const options = DRY_RUN
  ? { vus: 1, iterations: 2, thresholds, tags: tags('configuration') }
  : { vus: 50, duration: '30s', thresholds, tags: tags('configuration') };

export default function () {
  const deviceId = deviceIdFor();
  const response = http.get(
    `${API_URL}/api/v1/device/configuration?current_version=1`,
    { headers: deviceHeaders(deviceId), tags: { endpoint: 'configuration' } },
  );
  check(response, { 'configuration 200': (r) => r.status === 200 });
}
