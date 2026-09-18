import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import worker from '../cloud/worker.js';

const values = new Map();
const { privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
const env = { RSA_SIGNING_KEY: privateKey.export({ format: 'pem', type: 'pkcs8' }), WB_LICENSES: {
  get: async (key) => values.get(key) ?? null,
  put: async (key, value) => { values.set(key, value); }
} };

const requestTrial = () => worker.fetch(new Request('https://example.test/api/pay/create-order', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ mid: 'NEW-OR-EXISTING-CID', plan_id: 'free_trial_2days' })
}), env, {});

const started = Date.now();
const first = await requestTrial();
assert.equal(first.status, 200);
const issued = await first.json();
assert.equal(issued.ok, true);
assert.equal(issued.free, true);
const expiry = Date.parse(issued.expires_at.replace(' ', 'T'));
assert.ok(Math.abs(expiry - started - 48 * 3600 * 1000) < 3000);
const verified = await worker.fetch(new Request(
  'https://example.test/api/verify?key=' + encodeURIComponent(issued.license_key) + '&mid=new-or-existing-cid'
), env, {});
assert.equal(verified.status, 200);
assert.equal((await verified.json()).valid, true);

const second = await requestTrial();
assert.equal(second.status, 200);
const repeated = await second.json();
assert.equal(repeated.already_claimed, true);
assert.equal(repeated.expires_at, issued.expires_at);
assert.equal(repeated.license_key, issued.license_key);
assert.equal(values.size, 2);

console.log('Worker 48-hour trial and repeat claim checks passed');
