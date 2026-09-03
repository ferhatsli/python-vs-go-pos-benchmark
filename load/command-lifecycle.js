import http from 'k6/http';
import { check } from 'k6';
import { API_URL, DRY_RUN, deviceHeaders, tags, uniqueKey } from './common.js';

const commandVUs = DRY_RUN ? 1 : Number(__ENV.COMMAND_VUS || 10);
const commandBaseId = Number(__ENV.COMMAND_BASE_ID || 1);

export const options = {
  scenarios: {
    command_lifecycle: {
      executor: 'shared-iterations',
      vus: commandVUs,
      iterations: commandVUs,
      maxDuration: '30s',
    },
  },
  thresholds: { checks: ['rate==1'] },
  tags: tags('command-lifecycle'),
};

export default function () {
  const commandId = commandBaseId + (__VU - 1);
  const deviceId = commandId;
  const headers = deviceHeaders(deviceId);

  const pending = http.get(`${API_URL}/api/v1/device/commands/pending`, {
    headers,
    tags: { endpoint: 'commands-pending' },
  });
  check(pending, { 'pending 200': (r) => r.status === 200 });

  const acknowledge = http.post(`${API_URL}/api/v1/device/commands/${commandId}/acknowledge`, null, {
    headers,
    tags: { endpoint: 'command-acknowledge' },
  });
  check(acknowledge, { 'acknowledge 200': (r) => r.status === 200 });

  const resultKey = uniqueKey('command-result', String(commandId));
  const resultBody = JSON.stringify({ result: 'SUCCESS', code: null, message: null });
  const result = http.post(`${API_URL}/api/v1/device/commands/${commandId}/result`, resultBody, {
    headers: deviceHeaders(deviceId, resultKey),
    tags: { endpoint: 'command-result' },
  });
  check(result, { 'result 200': (r) => r.status === 200 });

  const duplicate = http.post(`${API_URL}/api/v1/device/commands/${commandId}/result`, resultBody, {
    headers: deviceHeaders(deviceId, resultKey),
    tags: { endpoint: 'command-result-duplicate' },
  });
  check(duplicate, {
    'duplicate result idempotent': (r) => r.status === 200 && r.json('data.status') === 'SUCCESS',
  });
}
