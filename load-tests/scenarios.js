import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import exec from 'k6/execution';

const data = JSON.parse(open('../artifacts/demo.json'));
const base = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const conflicts = new Counter('booking_conflicts');
export const options = {
  scenarios: {
    reads: {executor: 'constant-vus', vus: 10, duration: '30s', exec: 'reads'},
    bookings: {executor: 'shared-iterations', vus: 5, iterations: 50, exec: 'bookings'},
    contention: {executor: 'shared-iterations', vus: 10, iterations: 20, exec: 'contention'},
  },
  thresholds: {
    'http_req_duration{kind:read}': ['p(95)<200'],
    'http_req_duration{kind:write}': ['p(95)<500'],
    checks: ['rate>0.99'],
  },
  summaryTrendStats: ['avg', 'p(50)', 'p(95)', 'p(99)', 'max'],
};
const headers = {Authorization: `Bearer ${data.patient_token}`, 'Content-Type': 'application/json'};
export function reads() {
  const calls = [
    ['/api/v1/doctors?specialization=Ayurveda', {}],
    [`/api/v1/doctors/${data.doctor_id}/availability`, {}],
    ['/api/v1/consultations', {headers}],
    ['/api/v1/admin/analytics/overview', {headers: {Authorization: `Bearer ${data.admin_token}`}}],
  ];
  for (const [path, params] of calls) {
    const r = http.get(base + path, {...params, tags: {kind: 'read'}});
    check(r, {'read succeeds': r => r.status === 200});
  }
  sleep(0.1);
}
function book(slot, key) {
  const r = http.post(base + '/api/v1/consultations', JSON.stringify({availability_slot_id: slot, reason_for_visit: 'Synthetic load test'}),
    {headers: {...headers, 'Idempotency-Key': key}, tags: {kind: 'write'}});
  if (r.status === 409) conflicts.add(1);
  check(r, {'booking succeeds or conflicts': r => [201, 409].includes(r.status)});
  if (r.status === 201) {
    const detail = http.get(base + '/api/v1/consultations/' + r.json('id'), {headers, tags: {kind: 'read'}});
    check(detail, {'detail succeeds': r => r.status === 200});
  }
}
export function bookings() {
  const i = exec.scenario.iterationInTest;
  book(data.slots[i + 1], `load-${i}`);
}
export function contention() {
  book(data.slots[0], `contention-${exec.scenario.iterationInTest}`);
}
