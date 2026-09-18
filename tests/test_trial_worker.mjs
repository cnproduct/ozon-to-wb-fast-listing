import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import worker from '../cloud/worker.js';

const values = new Map();
const ipClaims = new Map();
const { privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
const env = { RSA_SIGNING_KEY: privateKey.export({ format: 'pem', type: 'pkcs8' }), WB_LICENSES: {
  get: async (key) => values.get(key) ?? null,
  put: async (key, value) => { values.set(key, value); }
}, TRIAL_IP_LIMITER: {
  getByName(name) {
    if (!ipClaims.has(name)) ipClaims.set(name, new Map());
    const claims = ipClaims.get(name);
    return {
      async reserve(hash) {
        const existing = claims.get(hash);
        if (existing) return existing.status === 'issued' ? existing : { status: 'pending' };
        if (claims.size >= 3) return { status: 'limit' };
        const token = crypto.randomUUID();
        claims.set(hash, { status: 'pending', token });
        return { status: 'reserved', token };
      },
      async complete(hash, token, license_key, expires_at, store_name) {
        assert.equal(claims.get(hash)?.token, token);
        claims.set(hash, { status: 'issued', license_key, expires_at, store_name });
      }
    };
  }
} };

const requestTrial = (mid = 'NEW-OR-EXISTING-CID', ip = '203.0.113.10') => worker.fetch(new Request('https://example.test/api/pay/create-order', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', ...(ip ? { 'CF-Connecting-IP': ip } : {}) },
  body: JSON.stringify({ mid, plan_id: 'free_trial_2days' })
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

assert.equal((await requestTrial('SECOND-CID')).status, 200);
assert.equal((await requestTrial('THIRD-CID')).status, 200);
const fourth = await requestTrial('FOURTH-CID');
assert.equal(fourth.status, 429);
assert.equal((await fourth.json()).error,
  '避免线路拥堵，您只允许3个试用窗口。如需使用更多窗口，请跟代理商申请付费授权窗口');
assert.equal((await requestTrial('FOURTH-CID', '203.0.113.11')).status, 200);
assert.equal((await requestTrial('NO-IP', '')).status, 503);

const parallel = await Promise.all(['A', 'B', 'C', 'D'].map(mid => requestTrial(mid, '2001:db8::1')));
assert.equal(parallel.filter(response => response.status === 200).length, 3);
assert.equal(parallel.filter(response => response.status === 429).length, 1);

console.log('Worker 48-hour trial, retry, and 3-window-per-IP checks passed');
