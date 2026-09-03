import http from 'k6/http';
import { check } from 'k6';
import { API_URL, deviceHeaders, tags } from './common.js';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: { checks: ['rate==1'] },
  tags: tags('smoke'),
};

export default function () {
  const deviceId = 1;
  const health = http.get(`${API_URL}/health`);
  check(health, { 'health 200': (r) => r.status === 200 });

  const heartbeat = http.post(
    `${API_URL}/api/v1/device/heartbeat`,
    JSON.stringify({ sequence: 1, app_version: 'k6-smoke', state: { source: 'k6' } }),
    { headers: deviceHeaders(deviceId) },
  );
  check(heartbeat, { 'heartbeat 200': (r) => r.status === 200 });

  const configuration = http.get(
    `${API_URL}/api/v1/device/configuration?current_version=1`,
    { headers: deviceHeaders(deviceId) },
  );
  check(configuration, { 'configuration 200': (r) => r.status === 200 });
}
