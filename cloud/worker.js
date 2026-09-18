import crypto from 'node:crypto';
import { Buffer } from 'node:buffer';

/**
 * Cloudflare Workers Commercial License & Anti-Piracy Gateway + Alipay Self-Service Cashier
 * Pricing: ¥600 RMB per store (单店商业授权 ¥600.00 / 店铺)
 * Zero-server, zero-maintenance global edge authentication, remote management, and automated Alipay license dispensing.
 */

// Embedded default credentials
const DEFAULT_ALIPAY_APP_ID = "2021007100605449";
const DEFAULT_ALIPAY_PRIVATE_KEY_B64 = "";

const DEFAULT_ALIPAY_PUBLIC_KEY_B64 = `MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwdOBuGCeyxVO+NCZuEiIVk+har+YaYrW7GzWS3AEPinZ5sb/2oqymr3Coa8JmcmW5sah59Fro3d8SJCkFroRniPOZn/HohxP+8hz9Zh0L5vIWUYPz+fDF675wxzg5TappT0gOgADio+8LtrbPaB5T7i0VgN2qfytDJkFgLvweMHJaLz/WoXNVhVAcOqwj611TX3KlckFebOQQbwoSW4juaPf4qYBRMPSGZxzMo3sNtwKUmd0YHk0wtsbIRacCvfCC0lIo9cjZ2XPLQj4tGRob/X9XUK6EjHpCUpPrRMm+jBlz5B9XoND6SEJy2xpVVnij1fe8ux6ZTkfTygH/Er1UwIDAQAB`;

const DEFAULT_RSA_SIGNING_KEY_B64 = "";

// Pricing Model: 2-Day Free Trial (¥0) & Single Store Monthly License (¥600 / month, 30 days)
const PLANS = {
  free_trial_2days: {
    id: "free_trial_2days",
    name: "2天全功能免费试用版",
    stores: 1,
    price: "0.00",
    original_price: "99.00",
    days: 2,
    desc: "48小时全功能免费体验 · 1店1码 1:1 独立隔离 · 莫斯科1仓现货秒级注入 · 试用满意随时升级"
  },
  single_store: {
    id: "single_store",
    name: "单店月度商业授权",
    stores: 1,
    price: "600.00",
    original_price: "999.00",
    days: 30,
    desc: "1:1 店铺专属互斥锁定 · 30天全功能极速搬家 · 50%大促折算 · 莫斯科1仓现货秒级注入 · 赠 1 次安全换店配额"
  },
  dual_store: {
    id: "dual_store",
    name: "双店月度套餐 (2 家店铺)",
    stores: 2,
    price: "1200.00",
    original_price: "1998.00",
    days: 30,
    desc: "支持 2 家 Wildberries 店铺独立授权 · 专属一对一上架技术指导 · 双店矩阵卖家推荐"
  }
};

/**
 * Deterministic JSON stringifier matching Python json.dumps(..., separators=(',', ':'), sort_keys=True)
 */
function canonicalJson(obj) {
  if (Array.isArray(obj)) {
    return '[' + obj.map(canonicalJson).join(',') + ']';
  }
  if (obj !== null && typeof obj === 'object') {
    const keys = Object.keys(obj).sort();
    return '{' + keys.map(k => JSON.stringify(k) + ':' + canonicalJson(obj[k])).join(',') + '}';
  }
  if (typeof obj === 'string') {
    return JSON.stringify(obj).replace(/[\u007f-\uffff]/g, c => {
      return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
    });
  }
  return JSON.stringify(obj);
}

/**
 * Node.js Crypto RSA-PSS SHA-256 license key generation
 */
function signLicenseKey(mid, customerName, storeName, days = 3650, maxSessions = 1, privKeyB64 = DEFAULT_RSA_SIGNING_KEY_B64, exactExpiry = false) {
  if (!privKeyB64) throw new Error('RSA_SIGNING_KEY is not configured');
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const iatStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  
  const expDate = new Date(now.getTime() + (days > 0 ? days : 3650) * 24 * 60 * 60 * 1000);
  const expStr = days > 0
    ? `${expDate.getFullYear()}-${pad(expDate.getMonth() + 1)}-${pad(expDate.getDate())} ${exactExpiry ? `${pad(expDate.getHours())}:${pad(expDate.getMinutes())}:${pad(expDate.getSeconds())}` : '23:59:59'}`
    : '2099-12-31 23:59:59';

  const payload = {
    v: '2.0',
    mid: mid.trim().toUpperCase(),
    name: (customerName || '商业客户').trim(),
    store: (storeName || '专属WB店铺').trim(),
    max_s: maxSessions,
    iat: iatStr,
    exp: expStr,
    perm: ['listing', 'pricing', 'stocks', 'fast_list']
  };

  const serialized = canonicalJson(payload);
  const cleanB64 = privKeyB64.replace(/-----BEGIN[A-Z\s]+-----/g, '').replace(/-----END[A-Z\s]+-----/g, '').replace(/[\r\n\s]+/g, '');
  const keyBuf = Buffer.from(cleanB64, 'base64');

  const sign = crypto.createSign('SHA256');
  sign.update(Buffer.from(serialized, 'utf8'));
  const signature = sign.sign({
    key: keyBuf,
    format: 'der',
    type: 'pkcs8',
    padding: crypto.constants.RSA_PKCS1_PSS_PADDING,
    saltLength: crypto.constants.RSA_PSS_SALTLEN_MAX_SIGN
  });

  const pkg = {
    p: payload,
    s: signature.toString('base64')
  };

  const licToken = Buffer.from(canonicalJson(pkg), 'utf8').toString('base64');
  return {
    license_key: 'LIC-RSA-' + licToken,
    payload
  };
}

const SHA256_DIGEST_INFO_PREFIX = Buffer.from('3031300d060960864801650304020105000420', 'hex');

function modPow(b, exp, mod) {
  let res = 1n;
  b = b % mod;
  while (exp > 0n) {
    if (exp % 2n === 1n) res = (res * b) % mod;
    b = (b * b) % mod;
    exp /= 2n;
  }
  return res;
}

function parseRsaKeyBigInt(keyB64) {
  const cleanB64 = keyB64.replace(/-----BEGIN[A-Z\s]+-----/g, '').replace(/-----END[A-Z\s]+-----/g, '').replace(/[\r\n\s]+/g, '');
  const buf = Buffer.from(cleanB64, 'base64');
  let pos = 0;
  function readByte() { return buf[pos++]; }
  function readLength() {
    let b = readByte();
    if (b < 0x80) return b;
    let numBytes = b & 0x7f;
    let len = 0;
    for (let i = 0; i < numBytes; i++) {
      len = (len << 8) | readByte();
    }
    return len;
  }
  function readInteger() {
    let tag = readByte();
    let len = readLength();
    let intBuf = buf.subarray(pos, pos + len);
    pos += len;
    if (intBuf.length === 0) return 0n;
    return BigInt('0x' + intBuf.toString('hex'));
  }

  if (buf[0] === 0x30) {
    readByte();
    readLength();
    let v = readInteger();
    if (v === 0n && buf[pos] === 0x30) {
      readByte();
      let algLen = readLength();
      pos += algLen;
      if (buf[pos] === 0x04) {
        readByte();
        readLength();
        if (buf[pos] === 0x30) {
          readByte();
          readLength();
          let rsaVer = readInteger();
          let n = readInteger();
          let e = readInteger();
          let d = readInteger();
          return { n, e, d };
        }
      }
    }
  }

  pos = 0;
  if (buf[0] === 0x30) {
    readByte();
    readLength();
    let v = readInteger();
    let n = readInteger();
    let e = readInteger();
    let d = readInteger();
    return { n, e, d };
  }
  throw new Error('Unsupported RSA private key format');
}

function parseRsaPubKeyBigInt(pubKeyB64) {
  const cleanB64 = pubKeyB64.replace(/-----BEGIN[A-Z\s]+-----/g, '').replace(/-----END[A-Z\s]+-----/g, '').replace(/[\r\n\s]+/g, '');
  const buf = Buffer.from(cleanB64, 'base64');
  let pos = 0;
  function readByte() { return buf[pos++]; }
  function readLength() {
    let b = readByte();
    if (b < 0x80) return b;
    let numBytes = b & 0x7f;
    let len = 0;
    for (let i = 0; i < numBytes; i++) {
      len = (len << 8) | readByte();
    }
    return len;
  }
  function readInteger() {
    let tag = readByte();
    let len = readLength();
    let intBuf = buf.subarray(pos, pos + len);
    pos += len;
    if (intBuf.length === 0) return 0n;
    return BigInt('0x' + intBuf.toString('hex'));
  }

  if (buf[0] === 0x30) {
    readByte();
    readLength();
    if (buf[pos] === 0x30) {
      readByte();
      let algLen = readLength();
      pos += algLen;
      if (buf[pos] === 0x03) {
        readByte();
        readLength();
        readByte(); // skip unused bits count
        if (buf[pos] === 0x30) {
          readByte();
          readLength();
          let n = readInteger();
          let e = readInteger();
          return { n, e };
        }
      }
    }
  }

  pos = 0;
  if (buf[0] === 0x30) {
    readByte();
    readLength();
    let n = readInteger();
    let e = readInteger();
    return { n, e };
  }
  throw new Error('Unsupported RSA public key format');
}

/**
 * RSASSA-PKCS1-v1_5 SHA-256 for Alipay Request signing
 */
function signAlipayParams(params, privKeyB64) {
  const keys = Object.keys(params)
    .filter(k => k !== 'sign' && params[k] !== undefined && params[k] !== null && params[k] !== '')
    .sort();
  const prestr = keys.map(k => `${k}=${params[k]}`).join('&');

  const { n, d } = parseRsaKeyBigInt(privKeyB64);
  const hash = crypto.createHash('sha256').update(Buffer.from(prestr, 'utf8')).digest();
  const digestInfo = Buffer.concat([SHA256_DIGEST_INFO_PREFIX, hash]);
  const psLen = 256 - 3 - digestInfo.length;
  const ps = Buffer.alloc(psLen, 0xff);
  const em = Buffer.concat([Buffer.from([0x00, 0x01]), ps, Buffer.from([0x00]), digestInfo]);

  const mBn = BigInt('0x' + em.toString('hex'));
  const sBn = modPow(mBn, d, n);

  let sHex = sBn.toString(16);
  while (sHex.length < 512) sHex = '0' + sHex;
  return Buffer.from(sHex, 'hex').toString('base64');
}

/**
 * RSASSA-PKCS1-v1_5 SHA-256 for Alipay Webhook Callback Verification
 */
function verifyAlipayNotify(params, pubKeyB64) {
  const sign = params.sign;
  if (!sign) return false;
  const keys = Object.keys(params)
    .filter(k => k !== 'sign' && k !== 'sign_type' && params[k] !== undefined && params[k] !== null && params[k] !== '')
    .sort();
  const prestr = keys.map(k => `${k}=${params[k]}`).join('&');

  try {
    const { n, e } = parseRsaPubKeyBigInt(pubKeyB64);
    const hash = crypto.createHash('sha256').update(Buffer.from(prestr, 'utf8')).digest();
    const digestInfo = Buffer.concat([SHA256_DIGEST_INFO_PREFIX, hash]);
    const psLen = 256 - 3 - digestInfo.length;
    const ps = Buffer.alloc(psLen, 0xff);
    const expectedEm = Buffer.concat([Buffer.from([0x00, 0x01]), ps, Buffer.from([0x00]), digestInfo]);

    const sBn = BigInt('0x' + Buffer.from(sign, 'base64').toString('hex'));
    const mBn = modPow(sBn, e, n);

    let mHex = mBn.toString(16);
    while (mHex.length < 512) mHex = '0' + mHex;
    const actualEm = Buffer.from(mHex, 'hex');

    return expectedEm.equals(actualEm);
  } catch (err) {
    console.error('Alipay verify error:', err);
    return false;
  }
}


function getLicenseKvKey(licenseKey) {
  if (!licenseKey) return '';
  if (licenseKey.startsWith('LIC-RSA-') || licenseKey.length > 256) {
    const hash = crypto.createHash('sha256').update(licenseKey).digest('hex');
    return 'LIC_HASH:' + hash;
  }
  return licenseKey;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // CORS Headers
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Admin-Secret",
    };

    if (method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    const adminSecret = env.ADMIN_SECRET || "";
    const alipayAppId = env.ALIPAY_APP_ID || DEFAULT_ALIPAY_APP_ID;
    const alipayPrivKey = env.ALIPAY_PRIVATE_KEY || DEFAULT_ALIPAY_PRIVATE_KEY_B64;
    const alipayPubKey = env.ALIPAY_PUBLIC_KEY || DEFAULT_ALIPAY_PUBLIC_KEY_B64;
    const rsaSignKeyB64 = env.RSA_SIGNING_KEY || DEFAULT_RSA_SIGNING_KEY_B64;

    // 1. Health Check
    if (path === "/" || path === "/health") {
      return new Response(JSON.stringify({
        status: "healthy",
        service: "Wildberries Commercial License & Alipay Payment Gateway",
        pricing_model: "¥600 RMB per store (单店商业授权 ¥600/店铺)",
        app_id: alipayAppId,
        timestamp: new Date().toISOString()
      }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 2. Client License Verification Endpoint: GET /api/verify?key=...&mid=...
    if (path === "/api/verify" && method === "GET") {
      const key = url.searchParams.get("key");
      const mid = url.searchParams.get("mid");

      if (!key) {
        return new Response(JSON.stringify({ valid: false, error: "Missing license key" }), {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      if (!env.WB_LICENSES) {
        return new Response(JSON.stringify({ valid: false, error: "KV namespace WB_LICENSES not bound" }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      const kvKey = getLicenseKvKey(key);
      let recordJson = await env.WB_LICENSES.get(kvKey);
      if (!recordJson && key.length <= 512) {
        recordJson = await env.WB_LICENSES.get(key);
      }
      if (!recordJson) {
        return new Response(JSON.stringify({ valid: false, error: "License not found or expired" }), {
          status: 404,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      let record;
      try {
        record = JSON.parse(recordJson);
      } catch (e) {
        return new Response(JSON.stringify({ valid: false, error: "Malformed license record" }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      if (record.status === "BANNED") {
        return new Response(JSON.stringify({
          valid: false,
          error: "License has been remotely REVOKED/BANNED by administrator",
          ban_reason: record.ban_reason || "Violation of terms"
        }), {
          status: 403,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      if (record.expires_at && record.expires_at !== "2099-12-31 23:59:59") {
        const expDate = new Date(record.expires_at.replace(" ", "T"));
        if (new Date() > expDate) {
          return new Response(JSON.stringify({ valid: false, error: "License has expired", expires_at: record.expires_at }), {
            status: 403,
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }
      }

      if (record.machine_id && mid && record.machine_id.toUpperCase() !== mid.trim().toUpperCase() && record.machine_id !== "*") {
        return new Response(JSON.stringify({
          valid: false,
          error: "Hardware mismatch: License is bound to another machine",
          bound_mid: record.machine_id,
          request_mid: mid
        }), {
          status: 403,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }

      if (!record.machine_id && mid) {
        record.machine_id = mid;
        record.first_activated_at = new Date().toISOString();
        await env.WB_LICENSES.put(kvKey, JSON.stringify(record));
      }

      record.last_verified_at = new Date().toISOString();
      await env.WB_LICENSES.put(kvKey, JSON.stringify(record));

      return new Response(JSON.stringify({
        valid: true,
        license_key: key,
        name: record.name,
        store_name: record.store_name || record.store || "",
        machine_id: record.machine_id,
        expires_at: record.expires_at,
        permissions: record.permissions || ["listing", "pricing", "stocks", "fast_list"]
      }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 3. Client Usage Reporting Endpoint: POST /api/report_usage
    if (path === "/api/report_usage" && method === "POST") {
      try {
        const body = await request.json();
        const { key, amount = 1 } = body;
        if (!key || !env.WB_LICENSES) {
          return new Response(JSON.stringify({ ok: false }), { status: 400, headers: corsHeaders });
        }
        const kvKey = getLicenseKvKey(key);
        let recordJson = await env.WB_LICENSES.get(kvKey);
        if (!recordJson && key.length <= 512) recordJson = await env.WB_LICENSES.get(key);
        if (recordJson) {
          const record = JSON.parse(recordJson);
          record.usage_count = (record.usage_count || 0) + Number(amount);
          record.last_used_at = new Date().toISOString();
          await env.WB_LICENSES.put(kvKey, JSON.stringify(record));
          return new Response(JSON.stringify({ ok: true, total_usage: record.usage_count }), {
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }
        return new Response(JSON.stringify({ ok: false, error: "License not found" }), { status: 404, headers: corsHeaders });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 3.1 Session Agent Binding API: POST /api/session/bind-agent
    if (path === "/api/session/bind-agent" && method === "POST") {
      try {
        const body = await request.json();
        const { cid, mid, agent_id } = body;
        if (!agent_id || (!cid && !mid) || !env.WB_LICENSES) {
          return new Response(JSON.stringify({ ok: false, error: "Missing agent_id or session identifier" }), {
            status: 400,
            headers: corsHeaders
          });
        }
        const cleanAgent = agent_id.trim();
        const boundData = {
          agent_id: cleanAgent,
          cid: cid || "",
          mid: mid || "",
          bound_at: new Date().toISOString()
        };
        if (cid) {
          await env.WB_LICENSES.put(`SESSION_AGENT:${cid}`, JSON.stringify(boundData));
        }
        if (mid) {
          await env.WB_LICENSES.put(`SESSION_AGENT:${mid}`, JSON.stringify(boundData));
        }
        let agentProfile = null;
        const agentRaw = await env.WB_LICENSES.get(`AGENT:${cleanAgent}`);
        if (agentRaw) {
          try { agentProfile = JSON.parse(agentRaw); } catch(e) {}
        }
        return new Response(JSON.stringify({
          ok: true,
          agent_id: cleanAgent,
          agent_name: agentProfile ? agentProfile.name : cleanAgent,
          bound_at: boundData.bound_at
        }), {
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ ok: false, error: err.message }), {
          status: 500,
          headers: corsHeaders
        });
      }
    }

    // 3.2 Session Agent Lookup API: GET /api/session/agent?cid=...&mid=...
    if (path === "/api/session/agent" && method === "GET") {
      try {
        const cid = url.searchParams.get("cid");
        const mid = url.searchParams.get("mid");
        if (!env.WB_LICENSES) return new Response(JSON.stringify({ ok: false }), { status: 500, headers: corsHeaders });
        let raw = null;
        if (cid) raw = await env.WB_LICENSES.get(`SESSION_AGENT:${cid}`);
        if (!raw && mid) raw = await env.WB_LICENSES.get(`SESSION_AGENT:${mid}`);
        if (raw) {
          const data = JSON.parse(raw);
          return new Response(JSON.stringify({ ok: true, ...data }), {
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }
        return new Response(JSON.stringify({ ok: false, error: "Not bound" }), {
          status: 404,
          headers: corsHeaders
        });
      } catch (err) {
        return new Response(JSON.stringify({ ok: false, error: err.message }), { status: 500, headers: corsHeaders });
      }
    }

    // ==========================================
    // 4. Alipay Cashier & Order APIs (¥600/Store)
    // ==========================================

    // 4.1 Cashier UI: GET /pay
    if (path === "/pay" && method === "GET") {
      const orderIdParam = url.searchParams.get("order_id") || "";
      const cidParam = url.searchParams.get("cid") || "";
      const planParam = url.searchParams.get("plan") || "single_store";
      const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Wildberries 极速上架助手 · 商业授权与免费试用</title>
  <style>
    :root {
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text-main: #f8fafc;
      --text-sub: #94a3b8;
      --border: #334155;
      --accent-green: #10b981;
      --alipay-blue: #1677ff;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .cashier-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      max-width: 620px;
      width: 100%;
      padding: 32px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.4);
    }
    .brand-header {
      text-align: center;
      margin-bottom: 24px;
    }
    .brand-badge {
      display: inline-block;
      padding: 4px 12px;
      background: rgba(99, 102, 241, 0.15);
      color: #818cf8;
      border: 1px solid rgba(99, 102, 241, 0.3);
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      margin-bottom: 12px;
    }
    h1 { font-size: 22px; font-weight: 700; color: #fff; }
    p.subtitle { color: var(--text-sub); font-size: 13px; margin-top: 6px; }

    .price-tag-banner {
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(16, 185, 129, 0.15));
      border: 1px solid rgba(99, 102, 241, 0.3);
      border-radius: 12px;
      padding: 14px 16px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .price-tag-info { display: flex; flex-direction: column; }
    .price-tag-label { font-size: 12px; color: #94a3b8; font-weight: 500; }
    .price-tag-desc { font-size: 13px; color: #38bdf8; font-weight: 600; margin-top: 2px; }
    .price-tag-num { font-size: 26px; font-weight: 800; color: #34d399; }
    .price-tag-num small { font-size: 13px; color: #94a3b8; font-weight: normal; }

    .form-group { margin-bottom: 18px; }
    label { display: block; font-size: 13px; font-weight: 600; color: #cbd5e1; margin-bottom: 8px; }
    .input-box {
      width: 100%;
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
      color: #fff;
      font-size: 14px;
      font-family: monospace;
      outline: none;
      transition: 0.2s;
    }
    .input-box:focus { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(99,102,241,0.25); }
    .input-tip { font-size: 11px; color: var(--text-sub); margin-top: 6px; line-height: 1.4; }
    .input-tip code { background: #334155; padding: 2px 6px; border-radius: 4px; color: #38bdf8; }

    .plans-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 22px;
    }
    @media (max-width: 540px) {
      .plans-grid { grid-template-columns: 1fr; }
    }
    .plan-card {
      background: #0f172a;
      border: 2px solid var(--border);
      border-radius: 12px;
      padding: 14px 10px;
      text-align: center;
      cursor: pointer;
      position: relative;
      transition: all 0.2s ease;
    }
    .plan-card:hover { border-color: #64748b; }
    .plan-card.active {
      border-color: var(--accent-green);
      background: rgba(16, 185, 129, 0.08);
    }
    .plan-badge {
      position: absolute;
      top: -10px;
      right: -6px;
      background: #10b981;
      color: #fff;
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 9999px;
      font-weight: 700;
    }
    .plan-title { font-size: 13px; font-weight: 600; color: #fff; margin-bottom: 6px; }
    .plan-price { font-size: 20px; font-weight: 800; color: #38bdf8; }
    .plan-price small { font-size: 11px; color: var(--text-sub); font-weight: normal; }
    .plan-orig { font-size: 11px; color: #64748b; text-decoration: line-through; margin-top: 2px; }

    .btn-pay {
      width: 100%;
      background: var(--alipay-blue);
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 14px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: background 0.2s;
    }
    .btn-pay.free-btn { background: #10b981; }
    .btn-pay.free-btn:hover { background: #059669; }
    .btn-pay:hover { background: #0958d9; }
    .btn-pay:disabled { opacity: 0.6; cursor: not-allowed; }

    .features-list {
      margin-top: 22px;
      border-top: 1px solid var(--border);
      padding-top: 16px;
    }
    .feature-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: var(--text-sub);
      margin-bottom: 6px;
    }
    .feature-item svg { width: 14px; height: 14px; color: var(--accent-green); flex-shrink: 0; }

    /* Success / Result View */
    .success-modal {
      display: none;
      background: #022c22;
      border: 1px solid #059669;
      border-radius: 12px;
      padding: 20px;
      margin-top: 20px;
      text-align: center;
    }
    .lic-display {
      background: #064e3b;
      border: 1px dashed #10b981;
      border-radius: 8px;
      padding: 12px;
      font-family: monospace;
      font-size: 11px;
      word-break: break-all;
      color: #a7f3d0;
      margin: 12px 0;
      text-align: left;
    }
    .btn-copy {
      background: var(--accent-green);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 8px 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-copy:hover { background: #059669; }
  </style>
</head>
<body>
  <div class="cashier-card">
    <div class="brand-header">
      <div class="brand-badge">⚡ Wildberries 官方智能上架助手</div>
      <h1>商业授权与免费试用收银台</h1>
      <p class="subtitle">单店 1:1 专属锁定 · 48小时免费体验 · ¥600/店铺/月度正式商业授权</p>
    </div>

    <div class="price-tag-banner">
      <div class="price-tag-info">
        <span class="price-tag-label" id="banner-label">收费计费标准</span>
        <span class="price-tag-desc" id="banner-desc">按 Wildberries 店铺计费 (1店1码)</span>
      </div>
      <div class="price-tag-num" id="banner-price">
        ¥600.00 <small>/ 店铺 / 月</small>
      </div>
    </div>

    <div id="checkout-section">
      <div class="form-group">
        <label>💻 目标电脑机器码 / 窗口 ID (Conversation ID) <span style="color: #ef4444;">*</span></label>
        <input type="text" id="mid-input" class="input-box" placeholder="MID-XXXX 或当前会话窗口 ID" value="${cidParam}" />
        <div class="input-tip">
          💡 获取方法：在 Antigravity 对话框中输入「<code>获取会话ID</code>」或「<code>获取机器码</code>」，粘贴在此。
        </div>
      </div>

      <div class="form-group">
        <label>🏪 绑定 Wildberries 店铺名称 / 简称 <span style="color: #ef4444;">*</span></label>
        <input type="text" id="store-input" class="input-box" placeholder="例如：我的WB一店 / 莫斯科优选店" style="font-family: sans-serif;" />
        <div class="input-tip">
          🛡️ 单窗口 1:1 专属店铺锁定，从物理根源杜绝商品串店与库存错乱隐患。
        </div>
      </div>

      <div class="form-group">
        <label>👤 客户联系人 / 手机号 (选填)</label>
        <input type="text" id="customer-input" class="input-box" placeholder="例如：张先生 (13800000000)" style="font-family: sans-serif;" />
      </div>

      <label>📦 选择店铺授权套餐</label>
      <div class="plans-grid">
        <div class="plan-card" onclick="selectPlan('free_trial_2days')" id="plan-free_trial_2days">
          <div class="plan-badge">0元体验</div>
          <div class="plan-title">2天免费试用</div>
          <div class="plan-price">¥0<small>/2天</small></div>
          <div class="plan-orig">原价 ¥99</div>
        </div>
        <div class="plan-card active" onclick="selectPlan('single_store')" id="plan-single_store">
          <div class="plan-badge">正式推荐</div>
          <div class="plan-title">单店月度授权</div>
          <div class="plan-price">¥600<small>/1家店/月</small></div>
          <div class="plan-orig">原价 ¥999</div>
        </div>
        <div class="plan-card" onclick="selectPlan('dual_store')" id="plan-dual_store">
          <div class="plan-title">双店月度套餐</div>
          <div class="plan-price">¥1200<small>/2家店/月</small></div>
          <div class="plan-orig">原价 ¥1998</div>
        </div>
      </div>

      <button id="pay-btn" class="btn-pay" onclick="handlePay()">
        <svg id="pay-svg" style="width: 20px; height: 20px;" viewBox="0 0 1024 1024" fill="currentColor">
          <path d="M793.6 128H230.4C174.08 128 128 174.08 128 230.4v563.2C128 849.92 174.08 896 230.4 896h563.2c56.32 0 102.4-46.08 102.4-102.4V230.4C896 174.08 849.92 128 793.6 128z m-204.8 542.72c-20.48 5.12-40.96 10.24-66.56 15.36 51.2 56.32 128 97.28 215.04 117.76-25.6 20.48-56.32 35.84-92.16 46.08-76.8-25.6-143.36-71.68-189.44-133.12-51.2 15.36-107.52 25.6-163.84 25.6-112.64 0-168.96-51.2-168.96-128 0-71.68 56.32-128 153.6-128 66.56 0 128 15.36 179.2 40.96V409.6H332.8v-71.68h122.88V256h81.92v81.92h143.36v71.68H537.6v76.8c56.32 15.36 112.64 35.84 163.84 66.56l-46.08 69.12c-20.48-10.24-40.96-20.48-66.56-30.72z m-168.96-20.48c-40.96-15.36-87.04-25.6-133.12-25.6-56.32 0-87.04 25.6-87.04 61.44 0 40.96 35.84 61.44 92.16 61.44 35.84 0 76.8-5.12 128-20.48V650.24z"/>
        </svg>
        <span id="btn-text">支付宝一键安全支付 (¥600.00) · 立即发码 (30天)</span>
      </button>

      <div class="features-list">
        <div class="feature-item">
          <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>
          前 2 天 100% 免费试用，支持 Ozon 标题、属性、多图、真实物理包装尺寸 100% 极速搬家至 WB
        </div>
        <div class="feature-item">
          <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>
          官方 EAN-13 条码自动批量申请、50% 官方大促折扣与莫斯科1仓现货秒级注入
        </div>
        <div class="feature-item">
          <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>
          单窗口 1:1 店铺互斥锁定防串店，保障账户资产与数据绝对安全
        </div>
      </div>
    </div>

    <!-- Success Result -->
    <div id="success-section" class="success-modal">
      <h2 style="color: #34d399; font-size: 18px; margin-bottom: 8px;">🎉 开通成功！专属店铺授权码已就绪</h2>
      <p style="font-size: 13px; color: #a7f3d0;">您的专属授权已签发并完成云端登记：</p>
      
      <div id="license-key-box" class="lic-display"></div>
      
      <button class="btn-copy" onclick="copyLicense()">📋 一键复制授权码</button>
      
      <div style="margin-top: 16px; font-size: 12px; color: #cbd5e1; text-align: left; background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; line-height: 1.6;">
        <strong style="color: #38bdf8;">🚀 激活上架步骤：</strong><br>
        1. 点击上方绿色按钮复制授权码；<br>
        2. 回到 Antigravity 聊天窗口中输入：<br>
        <code style="color: #34d399; font-weight: bold; background: #0f172a; padding: 2px 6px; border-radius: 4px;">激活授权 &lt;复制的授权码&gt;</code><br>
        3. 绑定您的 Wildberries 店铺：<br>
        <code style="color: #38bdf8; font-weight: bold; background: #0f172a; padding: 2px 6px; border-radius: 4px;">绑定店铺 店铺简称：我的WB店 API令牌：... 仓库ID：...</code><br>
        4. 输入 Ozon SKU 即可启动全自动极速搬家上架！
      </div>
    </div>
  </div>

  <script>
    let currentPlan = '${planParam}';
    if (!['free_trial_2days', 'single_store', 'dual_store'].includes(currentPlan)) {
      currentPlan = 'single_store';
    }

    const planPrices = { free_trial_2days: '0.00', single_store: '600.00', dual_store: '1200.00' };

    function selectPlan(planId) {
      currentPlan = planId;
      document.querySelectorAll('.plan-card').forEach(el => el.classList.remove('active'));
      const activeEl = document.getElementById('plan-' + planId);
      if (activeEl) activeEl.classList.add('active');

      const payBtn = document.getElementById('pay-btn');
      const btnText = document.getElementById('btn-text');
      const bannerPrice = document.getElementById('banner-price');
      const bannerDesc = document.getElementById('banner-desc');

      if (planId === 'free_trial_2days') {
        payBtn.classList.add('free-btn');
        btnText.innerText = '🎁 立即 0 元一键开通 2 天免费试用';
        bannerPrice.innerHTML = '¥0.00 <small>/ 免费体验 2 天</small>';
        bannerDesc.innerText = '48 小时全功能尝鲜体验 (1店1码)';
      } else if (planId === 'single_store') {
        payBtn.classList.remove('free-btn');
        btnText.innerText = '支付宝一键安全支付 (¥600.00) · 立即发码 (30天)';
        bannerPrice.innerHTML = '¥600.00 <small>/ 店铺 / 月</small>';
        bannerDesc.innerText = '单店月度商业授权 (自支付日起 30 天有效)';
      } else {
        payBtn.classList.remove('free-btn');
        btnText.innerText = '支付宝一键安全支付 (¥' + planPrices[planId] + ') · 立即发码';
        bannerPrice.innerHTML = '¥' + planPrices[planId] + ' <small>/ 2家店铺 / 月</small>';
        bannerDesc.innerText = '双店月度套餐 (自支付日起 30 天有效)';
      }
    }

    // Initialize with selected plan
    selectPlan(currentPlan);

    async function handlePay() {
      const mid = document.getElementById('mid-input').value.trim();
      const storeName = document.getElementById('store-input').value.trim();
      const customer = document.getElementById('customer-input').value.trim();

      if (!mid) {
        alert('请输入电脑机器码 (MID) 或会话窗口 ID (Conversation ID)！');
        document.getElementById('mid-input').focus();
        return;
      }
      if (!storeName) {
        alert('请输入要绑定的 Wildberries 店铺名称/简称！');
        document.getElementById('store-input').focus();
        return;
      }

      const payBtn = document.getElementById('pay-btn');
      payBtn.disabled = true;
      payBtn.innerText = currentPlan === 'free_trial_2days' ? '正在开通免费试用...' : '正在生成支付宝收银台...';

      try {
        const res = await fetch('/api/pay/create-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mid: mid,
            store_name: storeName,
            name: customer || storeName || (currentPlan === 'free_trial_2days' ? '免费试用卖家' : '商业客户'),
            plan_id: currentPlan
          })
        });
        const data = await res.json();
        if (!data.ok) {
          alert('开通/创建支付订单失败: ' + (data.error || '未知错误'));
          payBtn.disabled = false;
          selectPlan(currentPlan);
          return;
        }

        // Handle 0 RMB Free Trial
        if (data.free && data.license_key) {
          document.getElementById('checkout-section').style.display = 'none';
          document.getElementById('success-section').style.display = 'block';
          document.getElementById('license-key-box').innerText = data.license_key;
          return;
        }

        // Redirect to Alipay for paid plans
        if (data.pay_url) {
          window.location.href = data.pay_url;
        } else {
          alert('未获取到支付跳转链接');
          payBtn.disabled = false;
          selectPlan(currentPlan);
        }
      } catch (err) {
        alert('网络请求异常: ' + err.message);
        payBtn.disabled = false;
        selectPlan(currentPlan);
      }
    }

    function copyLicense() {
      const text = document.getElementById('license-key-box').innerText;
      navigator.clipboard.writeText(text).then(() => {
        alert('✅ 专属店铺授权码已成功复制到剪贴板！');
      }).catch(() => {
        alert('复制失败，请手动选择复制。');
      });
    }

    // Auto-check if returning with order_id
    const urlParams = new URLSearchParams(window.location.search);
    const existingOrderId = urlParams.get('order_id') || "${orderIdParam}";
    if (existingOrderId) {
      pollOrderStatus(existingOrderId);
    }

    async function pollOrderStatus(orderId) {
      try {
        const res = await fetch('/api/pay/order-status?order_id=' + encodeURIComponent(orderId));
        const data = await res.json();
        if (data.ok && data.status === 'PAID') {
          document.getElementById('checkout-section').style.display = 'none';
          document.getElementById('success-section').style.display = 'block';
          document.getElementById('license-key-box').innerText = data.license_key;
        } else {
          setTimeout(() => pollOrderStatus(orderId), 2000);
        }
      } catch (e) {
        setTimeout(() => pollOrderStatus(orderId), 3000);
      }
    }
  </script>
</body>
</html>`;

      return new Response(html, {
        headers: { "Content-Type": "text/html; charset=utf-8" }
      });
    }

    // 4.2 Create Order: POST /api/pay/create-order
    if (path === "/api/pay/create-order" && method === "POST") {
      try {
        const body = await request.json();
        const { mid, store_name = "我的WB店铺", name = "商业客户", plan_id = "single_store", agent_id = "" } = body;

        if (!mid) {
          return new Response(JSON.stringify({ ok: false, error: "缺少机器码 (MID) 或会话 ID" }), {
            status: 400,
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }

        let orderAgentId = (agent_id || "").trim();
        if (!orderAgentId && env.WB_LICENSES && mid) {
          const sessionAgentRaw = await env.WB_LICENSES.get(`SESSION_AGENT:${mid.trim()}`);
          if (sessionAgentRaw) {
            try {
              const sa = JSON.parse(sessionAgentRaw);
              if (sa.agent_id) orderAgentId = sa.agent_id;
            } catch(e) {}
          }
        }

        const plan = PLANS[plan_id] || PLANS.single_store;

        // Special handling for Free Trial (¥0.00)
        if (plan.id === "free_trial_2days" || plan.price === "0.00") {
          if (!rsaSignKeyB64) {
            return new Response(JSON.stringify({ ok: false, error: "试用签名密钥未配置" }), {
              status: 503, headers: { ...corsHeaders, "Content-Type": "application/json" }
            });
          }
          const targetId = mid.trim().toUpperCase();
          if (!env.WB_LICENSES) {
            return new Response(JSON.stringify({ ok: false, error: "试用授权存储未配置" }), {
              status: 503, headers: { ...corsHeaders, "Content-Type": "application/json" }
            });
          }
          const claimKey = `TRIAL_20260918_CID:${crypto.createHash('sha256').update(targetId).digest('hex')}`;
          const existingClaim = await env.WB_LICENSES.get(claimKey);
          if (existingClaim) {
            const existing = JSON.parse(existingClaim);
            // A client can lose the first response after the claim was saved.
            // Return the same grant so retries never mint a second 48-hour window.
            const issuedRecord = existing.license_key_hash
              ? await env.WB_LICENSES.get(existing.license_key_hash)
              : null;
            if (issuedRecord) {
              const issued = JSON.parse(issuedRecord);
              if (issued.key && issued.type === "RSA-FREE-TRIAL") {
                return new Response(JSON.stringify({
                  ok: true, free: true, already_claimed: true,
                  license_key: issued.key, expires_at: existing.expires_at,
                  store_name: issued.store_name, plan_name: plan.name
                }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
              }
            }
            return new Response(JSON.stringify({
              ok: false, already_claimed: true, expires_at: existing.expires_at,
              error: "此会话已领取 2 天免费试用；重复申请不会重置有效期"
            }), { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } });
          }
          const customerName = (name || "免费试用卖家").trim();
          const storeName = (store_name || "试用WB店铺").trim();
          const { license_key, payload } = signLicenseKey(targetId, customerName, storeName, 2, 1, rsaSignKeyB64, true);

          if (env.WB_LICENSES) {
            const licKvKey = getLicenseKvKey(license_key);
            const licRecord = {
              key: license_key,
              name: customerName,
              store_name: storeName,
              machine_id: targetId,
              max_sessions: 1,
              expires_at: payload.exp,
              type: "RSA-FREE-TRIAL",
              created_at: new Date().toISOString(),
              source: orderAgentId ? `AGENT:${orderAgentId}` : "FREE_TRIAL_2DAYS",
              agent_id: orderAgentId,
              order_id: `TRIAL_${Date.now()}`,
              amount: "0.00",
              activated_sessions: []
            };
            await env.WB_LICENSES.put(licKvKey, JSON.stringify(licRecord));
            await env.WB_LICENSES.put(claimKey, JSON.stringify({ license_key_hash: licKvKey, expires_at: payload.exp }));
          }

          return new Response(JSON.stringify({
            ok: true,
            free: true,
            license_key: license_key,
            expires_at: payload.exp,
            store_name: storeName,
            plan_name: plan.name,
            message: "🎉 2天全功能免费试用开通成功！"
          }), {
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }

        if (!rsaSignKeyB64 || !alipayPrivKey) {
          return new Response(JSON.stringify({ ok: false, error: "商业授权签名或支付密钥未配置" }), {
            status: 503, headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }

        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const timeStr = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
        const orderId = `WB_ORD_${timeStr}_${Math.random().toString(36).substring(2, 7).toUpperCase()}`;

        // Prepare Alipay page.pay parameters
        const notifyUrl = `${url.origin}/api/pay/alipay-callback`;
        const returnUrl = `${url.origin}/pay?order_id=${orderId}`;

        const passbackObj = {
          mid: mid.trim().toUpperCase(),
          name: name.trim(),
          store: store_name.trim(),
          days: plan.days,
          stores: plan.stores,
          plan_id: plan.id,
          agent_id: orderAgentId
        };

        const bizContent = {
          out_trade_no: orderId,
          total_amount: plan.price,
          subject: `Wildberries极速上架助手-${plan.name}`,
          product_code: "FAST_INSTANT_TRADE_PAY",
          body: JSON.stringify(passbackObj),
          passback_params: encodeURIComponent(JSON.stringify(passbackObj))
        };

        const nowFormat = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
        
        const params = {
          app_id: alipayAppId,
          method: "alipay.trade.page.pay",
          format: "JSON",
          return_url: returnUrl,
          notify_url: notifyUrl,
          charset: "utf-8",
          sign_type: "RSA2",
          timestamp: nowFormat,
          version: "1.0",
          biz_content: JSON.stringify(bizContent)
        };

        const sign = signAlipayParams(params, alipayPrivKey);
        params.sign = sign;

        // Build redirect URL
        const queryStr = Object.keys(params).map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`).join('&');
        const payUrl = `https://openapi.alipay.com/gateway.do?${queryStr}`;

        // Save Pending Order into KV
        if (env.WB_LICENSES) {
          const orderRecord = {
            order_id: orderId,
            status: "PENDING",
            machine_id: mid.trim().toUpperCase(),
            customer_name: name.trim(),
            store_name: store_name.trim(),
            plan_id: plan.id,
            plan_name: plan.name,
            amount: plan.price,
            stores: plan.stores,
            days: plan.days,
            agent_id: orderAgentId,
            created_at: nowFormat
          };
          await env.WB_LICENSES.put(`ORD:${orderId}`, JSON.stringify(orderRecord), { expirationTtl: 86400 * 7 });
        }

        return new Response(JSON.stringify({
          ok: true,
          order_id: orderId,
          amount: plan.price,
          plan_name: plan.name,
          store_name: store_name.trim(),
          pay_url: payUrl
        }), {
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ ok: false, error: err.message, stack: err.stack }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      }
    }

    // 4.3 Alipay Webhook Callback: POST /api/pay/alipay-callback
    if (path === "/api/pay/alipay-callback" && method === "POST") {
      try {
        const formData = await request.formData();
        const params = {};
        for (const [k, v] of formData.entries()) {
          params[k] = v;
        }

        // Verify Alipay Signature
        const isValid = verifyAlipayNotify(params, alipayPubKey);
        if (!isValid) {
          console.error("Alipay Webhook signature verification failed!");
          return new Response("failure", { status: 400 });
        }

        const tradeStatus = params.trade_status;
        const outTradeNo = params.out_trade_no;
        const tradeNo = params.trade_no;
        const totalAmount = params.total_amount;

        if (tradeStatus === "TRADE_SUCCESS" || tradeStatus === "TRADE_FINISHED") {
          let orderInfo = null;
          if (env.WB_LICENSES) {
            const ordJson = await env.WB_LICENSES.get(`ORD:${outTradeNo}`);
            if (ordJson) {
              orderInfo = JSON.parse(ordJson);
            }
          }

          // Extract passback params
          let extra = {};
          if (params.passback_params) {
            try {
              extra = JSON.parse(decodeURIComponent(params.passback_params));
            } catch (e) {}
          }

          const isAgentRecharge = extra.type === "AGENT_RECHARGE" || (orderInfo && orderInfo.type === "AGENT_RECHARGE");

          if (isAgentRecharge) {
            const agentId = extra.agent_id || (orderInfo && orderInfo.agent_id);
            if (agentId && env.WB_LICENSES) {
              const agentRaw = await env.WB_LICENSES.get(`AGENT:${agentId}`);
              if (agentRaw) {
                const ag = JSON.parse(agentRaw);
                const addAmount = Number(totalAmount) || Number(extra.amount) || Number(orderInfo && orderInfo.amount) || 0;
                ag.balance = Number((Number(ag.balance || 0) + addAmount).toFixed(2));
                ag.last_recharged_at = new Date().toISOString();
                await env.WB_LICENSES.put(`AGENT:${agentId}`, JSON.stringify(ag));

                // Update order status in KV
                const updatedOrder = {
                  ...(orderInfo || {}),
                  order_id: outTradeNo,
                  type: "AGENT_RECHARGE",
                  agent_id: agentId,
                  agent_name: ag.name,
                  status: "PAID",
                  trade_no: tradeNo,
                  amount: totalAmount,
                  paid_at: new Date().toISOString()
                };
                await env.WB_LICENSES.put(`ORD:${outTradeNo}`, JSON.stringify(updatedOrder), { expirationTtl: 86400 * 30 });
              }
            }
            return new Response("success", { status: 200, headers: { "Content-Type": "text/plain" } });
          }

          const mid = extra.mid || (orderInfo && orderInfo.machine_id) || "MID-UNKNOWN";
          const customerName = extra.name || (orderInfo && orderInfo.customer_name) || "支付宝客户";
          const storeName = extra.store || (orderInfo && orderInfo.store_name) || "Wildberries店铺";
          const days = Number(extra.days || (orderInfo && orderInfo.days) || 3650);
          const agentId = (extra.agent_id || (orderInfo && orderInfo.agent_id) || "").trim();

          // Sign the RSA license
          const { license_key, payload } = signLicenseKey(mid, customerName, storeName, days, 1, rsaSignKeyB64);

          // Save license to KV
          if (env.WB_LICENSES) {
            const licKvKey = getLicenseKvKey(license_key);
            const licRecord = {
              key: license_key,
              name: customerName,
              store_name: storeName,
              machine_id: mid,
              max_sessions: 1,
              expires_at: payload.exp,
              type: "RSA-PSS-SHA256",
              created_at: new Date().toISOString(),
              source: agentId ? `AGENT:${agentId}` : "ALIPAY_SELF_SERVICE",
              agent_id: agentId,
              trade_no: tradeNo,
              order_id: outTradeNo,
              amount: totalAmount,
              activated_sessions: []
            };
            await env.WB_LICENSES.put(licKvKey, JSON.stringify(licRecord));

            // If an agent is associated, attribute metrics
            if (agentId) {
              const agentRaw = await env.WB_LICENSES.get(`AGENT:${agentId}`);
              if (agentRaw) {
                try {
                  const ag = JSON.parse(agentRaw);
                  ag.total_stores_issued = Number(ag.total_stores_issued || 0) + 1;
                  ag.total_direct_revenue = Number((Number(ag.total_direct_revenue || 0) + Number(totalAmount || 0)).toFixed(2));
                  await env.WB_LICENSES.put(`AGENT:${agentId}`, JSON.stringify(ag));
                } catch(e) {}
              }
            }

            // Update order status
            const updatedOrder = {
              ...(orderInfo || {}),
              order_id: outTradeNo,
              status: "PAID",
              trade_no: tradeNo,
              amount: totalAmount,
              machine_id: mid,
              customer_name: customerName,
              store_name: storeName,
              license_key: license_key,
              expires_at: payload.exp,
              agent_id: agentId,
              paid_at: new Date().toISOString()
            };
            await env.WB_LICENSES.put(`ORD:${outTradeNo}`, JSON.stringify(updatedOrder), { expirationTtl: 86400 * 30 });
          }

          return new Response("success", { status: 200, headers: { "Content-Type": "text/plain" } });
        }

        return new Response("success", { status: 200 });
      } catch (err) {
        console.error("Alipay callback error:", err);
        return new Response("failure", { status: 500 });
      }
    }

    // 4.4 Check Order Status: GET /api/pay/order-status?order_id=...
    if (path === "/api/pay/order-status" && method === "GET") {
      const orderId = url.searchParams.get("order_id");
      if (!orderId || !env.WB_LICENSES) {
        return new Response(JSON.stringify({ ok: false, error: "Missing order_id" }), { status: 400, headers: corsHeaders });
      }

      const ordJson = await env.WB_LICENSES.get(`ORD:${orderId}`);
      if (!ordJson) {
        return new Response(JSON.stringify({ ok: false, status: "NOT_FOUND" }), { status: 404, headers: corsHeaders });
      }

      const ord = JSON.parse(ordJson);
      return new Response(JSON.stringify({
        ok: true,
        status: ord.status,
        license_key: ord.license_key || "",
        store_name: ord.store_name || "",
        expires_at: ord.expires_at || "",
        machine_id: ord.machine_id || "",
        amount: ord.amount || ""
      }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // ==========================================
    // 5. Multi-Agent Reseller System (代理商分销体系)
    // Tiered Wholesale Pricing:
    // - 0 ~ 100 stores cumulative: ¥240.00 / store
    // - 101+ stores cumulative: ¥180.00 / store
    // ==========================================

    function getAgentTierPrice(totalStoresIssued) {
      return Number(totalStoresIssued || 0) < 100 ? 240.00 : 180.00;
    }

    // Helper: Find agent by token (O(1) direct index + scan fallback)
    async function findAgentByToken(token) {
      if (!token || !env.WB_LICENSES) return null;
      const agentId = await env.WB_LICENSES.get(`AGENT_TOKEN:${token}`);
      if (agentId) {
        const raw = await env.WB_LICENSES.get(`AGENT:${agentId}`);
        if (raw) {
          try { return { key: `AGENT:${agentId}`, data: JSON.parse(raw) }; } catch (e) {}
        }
      }
      const list = await env.WB_LICENSES.list({ prefix: "AGENT:" });
      for (const k of list.keys) {
        const raw = await env.WB_LICENSES.get(k.name);
        if (raw) {
          try {
            const obj = JSON.parse(raw);
            if (obj.token === token) {
              if (obj.agent_id) await env.WB_LICENSES.put(`AGENT_TOKEN:${token}`, obj.agent_id);
              return { key: k.name, data: obj };
            }
          } catch (e) {}
        }
      }
      return null;
    }

    // Helper: Find agent by username (O(1) direct index + scan fallback)
    async function findAgentByUsername(username) {
      if (!username || !env.WB_LICENSES) return null;
      const cleanUser = username.trim().toLowerCase();
      const agentId = await env.WB_LICENSES.get(`AGENT_USER:${cleanUser}`);
      if (agentId) {
        const raw = await env.WB_LICENSES.get(`AGENT:${agentId}`);
        if (raw) {
          try { return { key: `AGENT:${agentId}`, data: JSON.parse(raw) }; } catch (e) {}
        }
      }
      const list = await env.WB_LICENSES.list({ prefix: "AGENT:" });
      for (const k of list.keys) {
        const raw = await env.WB_LICENSES.get(k.name);
        if (raw) {
          try {
            const obj = JSON.parse(raw);
            if (obj.username && obj.username.trim().toLowerCase() === cleanUser) {
              if (obj.agent_id) await env.WB_LICENSES.put(`AGENT_USER:${cleanUser}`, obj.agent_id);
              return { key: k.name, data: obj };
            }
          } catch (e) {}
        }
      }
      return null;
    }

    // 5.1 Agent Login API: POST /api/agent/login
    if (path === "/api/agent/login" && method === "POST") {
      try {
        const { username, password } = await request.json();
        if (!username || !password) {
          return new Response(JSON.stringify({ ok: false, error: "请输入登录用户名与密码" }), { status: 400, headers: corsHeaders });
        }
        const found = await findAgentByUsername(username);
        if (!found || found.data.password !== password) {
          return new Response(JSON.stringify({ ok: false, error: "用户名或密码错误" }), { status: 401, headers: corsHeaders });
        }
        if (found.data.status === "FROZEN") {
          return new Response(JSON.stringify({ ok: false, error: "该代理商账号已被冻结，请联系管理员" }), { status: 403, headers: corsHeaders });
        }
        return new Response(JSON.stringify({
          ok: true,
          token: found.data.token,
          agent_id: found.data.agent_id,
          name: found.data.name,
          username: found.data.username
        }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
      } catch (err) {
        return new Response(JSON.stringify({ ok: false, error: err.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 5.2 Agent Info & Dashboard Data API: POST /api/agent/info
    if (path === "/api/agent/info" && (method === "POST" || method === "GET")) {
      try {
        let token = url.searchParams.get("token");
        if (!token && method === "POST") {
          try {
            const body = await request.json();
            token = body.token;
          } catch (e) {}
        }
        if (!token) {
          const authHeader = request.headers.get("Authorization") || "";
          if (authHeader.startsWith("Bearer ")) token = authHeader.substring(7);
        }
        const found = await findAgentByToken(token);
        if (!found) {
          return new Response(JSON.stringify({ ok: false, error: "未授权或登录已过期" }), { status: 401, headers: corsHeaders });
        }
        const ag = found.data;
        const totalIssued = Number(ag.total_stores_issued || 0);
        const tierPrice = getAgentTierPrice(totalIssued);

        // Fetch recent licenses issued by this agent
        const list = await env.WB_LICENSES.list();
        const myLicenses = [];
        for (const k of list.keys) {
          if (!k.name.startsWith("AGENT:") && !k.name.startsWith("ORD:") && !k.name.startsWith("ADMIN_")) {
            const val = await env.WB_LICENSES.get(k.name);
            if (val) {
              try {
                const parsed = JSON.parse(val);
                if (parsed.source === `AGENT:${ag.agent_id}`) {
                  myLicenses.push({ key: parsed.key || k.name, ...parsed });
                }
              } catch (e) {}
            }
          }
        }
        myLicenses.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));

        return new Response(JSON.stringify({
          ok: true,
          agent: {
            agent_id: ag.agent_id,
            name: ag.name,
            username: ag.username || ag.agent_id,
            balance: Number(ag.balance || 0),
            total_stores_issued: totalIssued,
            tier_price: tierPrice,
            status: ag.status || "ACTIVE",
            created_at: ag.created_at
          },
          licenses: myLicenses.slice(0, 50)
        }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
      } catch (err) {
        return new Response(JSON.stringify({ ok: false, error: err.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 5.3 Agent Change Password API: POST /api/agent/change-password
    if (path === "/api/agent/change-password" && method === "POST") {
      try {
        const { token, old_password, new_password } = await request.json();
        if (!token) return new Response(JSON.stringify({ ok: false, error: "缺少安全 Token" }), { status: 401, headers: corsHeaders });
        if (!new_password || new_password.length < 6) {
          return new Response(JSON.stringify({ ok: false, error: "新密码长度至少需要 6 位" }), { status: 400, headers: corsHeaders });
        }
        const found = await findAgentByToken(token);
        if (!found) return new Response(JSON.stringify({ ok: false, error: "无效的 Token" }), { status: 401, headers: corsHeaders });
        if (found.data.password && found.data.password !== old_password) {
          return new Response(JSON.stringify({ ok: false, error: "原密码不正确" }), { status: 400, headers: corsHeaders });
        }
        found.data.password = new_password;
        found.data.password_updated_at = new Date().toISOString();
        await env.WB_LICENSES.put(found.key, JSON.stringify(found.data));
        return new Response(JSON.stringify({ ok: true, message: "密码修改成功！" }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
      } catch (err) {
        return new Response(JSON.stringify({ ok: false, error: err.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 5.4 Agent Portal UI: GET /agent
    if (path === "/agent" && method === "GET") {
      const queryToken = url.searchParams.get("token") || "";

      const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>代理商独立发卡平台 · Wildberries 极速搬家</title>
  <style>
    :root {
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --accent-green: #10b981;
      --accent-blue: #38bdf8;
      --text: #f8fafc;
      --text-sub: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .container { max-width: 1000px; margin: 0 auto; }
    
    #login-section { max-width: 420px; margin: 60px auto; background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
    .login-title { font-size: 20px; font-weight: 700; text-align: center; margin-bottom: 8px; color: #fff; }
    .login-sub { font-size: 13px; color: var(--text-sub); text-align: center; margin-bottom: 24px; }
    
    #dashboard-section { display: none; }
    .header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 1px solid var(--border); margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
    h1 { font-size: 22px; font-weight: 700; color: #fff; }
    .agent-header-right { display: flex; align-items: center; gap: 12px; }
    .agent-tag { background: rgba(99,102,241,0.2); color: #818cf8; padding: 6px 14px; border-radius: 9999px; font-size: 13px; font-weight: 600; border: 1px solid rgba(99,102,241,0.3); }
    .btn-sm { padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; border: 1px solid var(--border); background: #334155; color: #fff; transition: 0.15s; }
    .btn-sm:hover { background: #475569; }
    .btn-recharge { background: #059669; color: #fff; border: none; font-weight: 700; cursor: pointer; }
    .btn-recharge:hover { background: #047857; }
    .btn-logout { background: rgba(239,68,68,0.2); color: #f87171; border-color: rgba(239,68,68,0.4); }
    .btn-logout:hover { background: rgba(239,68,68,0.3); }

    .preset-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
    .preset-btn { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 12px 10px; text-align: center; cursor: pointer; transition: 0.15s; }
    .preset-btn:hover { border-color: #6366f1; background: #1e293b; }
    .preset-btn.active { border-color: #10b981; background: rgba(16, 185, 129, 0.15); box-shadow: 0 0 0 1px #10b981; }

    .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
    @media (max-width: 640px) { .stats-grid { grid-template-columns: 1fr; } }
    .stat-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
    .stat-label { font-size: 12px; color: var(--text-sub); font-weight: 600; margin-bottom: 6px; }
    .stat-num { font-size: 28px; font-weight: 800; }
    .stat-desc { font-size: 11px; color: #64748b; margin-top: 4px; }
    
    .tier-box { background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); border-radius: 12px; padding: 16px 20px; margin-bottom: 24px; }
    .tier-header { display: flex; justify-content: space-between; align-items: center; font-size: 13px; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
    .progress-bg { background: #334155; height: 8px; border-radius: 4px; overflow: hidden; }
    .progress-fill { background: linear-gradient(90deg, #6366f1, #10b981); height: 100%; border-radius: 4px; width: 0%; transition: width 0.4s; }
    
    .main-grid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 20px; margin-bottom: 24px; }
    @media (max-width: 768px) { .main-grid { grid-template-columns: 1fr; } }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 24px; }
    .card h2 { font-size: 16px; font-weight: 700; margin-bottom: 16px; color: #fff; }
    
    .form-group { margin-bottom: 16px; }
    label { display: block; font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; }
    .input-box { width: 100%; background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; color: #fff; font-size: 14px; outline: none; transition: 0.15s; }
    .input-box:focus { border-color: var(--primary); }
    .input-tip { font-size: 11px; color: var(--text-sub); margin-top: 4px; }
    
    .btn-primary { width: 100%; background: var(--primary); color: #fff; border: none; border-radius: 8px; padding: 12px; font-size: 14px; font-weight: 700; cursor: pointer; transition: 0.2s; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-issue { width: 100%; background: var(--accent-green); color: #fff; border: none; border-radius: 8px; padding: 12px; font-size: 14px; font-weight: 700; cursor: pointer; transition: 0.2s; }
    .btn-issue:hover { background: #059669; }
    .btn-issue:disabled { opacity: 0.5; cursor: not-allowed; }
    
    .lic-result { display: none; background: #064e3b; border: 1px dashed #10b981; border-radius: 8px; padding: 14px; margin-top: 16px; font-size: 12px; }
    .lic-text { font-family: monospace; word-break: break-all; color: #a7f3d0; background: #022c22; padding: 8px; border-radius: 4px; margin: 8px 0; }
    .btn-copy { background: #10b981; color: #fff; border: none; border-radius: 4px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
    
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }
    th { color: var(--text-sub); font-weight: 600; background: #0f172a; }

    .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px); z-index: 999; align-items: center; justify-content: center; }
    .modal-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 24px; width: 100%; max-width: 400px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }
  </style>
</head>
<body>
  <div class="container">
    <div id="login-section">
      <div class="login-title">🤝 代理商平台登录</div>
      <div class="login-sub">Wildberries 搬家上架 · 独立发卡控制台</div>
      
      <div class="form-group">
        <label>👤 登录用户名 (Username)</label>
        <input type="text" id="login-username" class="input-box" placeholder="请输入代理商账号" />
      </div>
      <div class="form-group">
        <label>🔑 登录密码 (Password)</label>
        <input type="password" id="login-password" class="input-box" placeholder="请输入密码" />
      </div>
      <button class="btn-primary" onclick="doLogin()">立即登录控制台</button>
      <div id="login-error" style="color: #f87171; font-size: 12px; margin-top: 12px; text-align: center; display: none;"></div>
    </div>

    <div id="dashboard-section">
      <div class="header">
        <div>
          <h1>🤝 代理商自助发码平台</h1>
          <div style="font-size: 12px; color: var(--text-sub); margin-top: 4px;">自主收款 · 自由定价 · 阶梯出厂结算</div>
        </div>
        <div class="agent-header-right">
          <div class="agent-tag" id="agent-tag-name">🏢 代理商加载中...</div>
          <button class="btn-sm btn-recharge" onclick="openRechargeModal()">💳 扫码充值</button>
          <button class="btn-sm" onclick="openChangePwdModal()">🔑 修改密码</button>
          <button class="btn-sm btn-logout" onclick="doLogout()">🚪 退出登录</button>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <div>
              <div class="stat-label">💰 账户预存可用余额</div>
              <div class="stat-num" id="stat-balance" style="color: #34d399;">¥0.00</div>
            </div>
            <button class="btn-sm btn-recharge" onclick="openRechargeModal()" style="margin-top:2px;">💳 充值</button>
          </div>
          <div class="stat-desc">每发一家店铺按当前阶梯出厂价扣除</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">🏪 累计开通店铺数</div>
          <div class="stat-num" id="stat-issued" style="color: #38bdf8;">0 <small style="font-size:14px;color:#94a3b8;">家</small></div>
          <div class="stat-desc">所有开通店铺累计计入阶梯出厂价</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">🏷️ 当前出厂单价</div>
          <div class="stat-num" id="stat-tier" style="color: #a78bfa;">¥240.00 <small style="font-size:14px;color:#94a3b8;">/ 店</small></div>
          <div class="stat-desc" id="stat-tier-desc">0-100家档 (¥240/店)</div>
        </div>
      </div>

      <div class="tier-box">
        <div class="tier-header">
          <span>📈 <strong>阶梯进阶进度</strong>: 当前已开通 <strong id="tier-issued-count">0</strong> / 100 家</span>
          <span id="tier-tip" style="color: #38bdf8; font-weight: 600;">还需开通 100 家即可享 ¥180/店 特惠出厂价！</span>
        </div>
        <div class="progress-bg">
          <div class="progress-fill" id="tier-progress-bar"></div>
        </div>
      </div>

      <div class="main-grid">
        <div class="card">
          <h2>⚡ 一键生成客户专属授权码</h2>
          <div class="form-group">
            <label>💻 客户会话窗口 ID (Conversation ID) 或机器码 (MID) <span style="color: #ef4444;">*</span></label>
            <input type="text" id="mid-input" class="input-box" placeholder="例如：ec2395ce-cbc0-49b4... 或 MID-XXXX" />
            <div class="input-tip">💡 客户在聊天框输入「<code>获取会话ID</code>」后发给您，粘贴在此。</div>
          </div>
          <div class="form-group">
            <label>🏪 客户 Wildberries 店铺名称 / 简称 <span style="color: #ef4444;">*</span></label>
            <input type="text" id="store-input" class="input-box" placeholder="例如：张总WB一店 / 莫斯科优选" />
          </div>
          <div class="form-group">
            <label>👤 客户联系人 / 手机号 (选填)</label>
            <input type="text" id="customer-input" class="input-box" placeholder="例如：张总 (13800000000)" />
          </div>
          <div class="form-group">
            <label>⏳ 授权有效天数</label>
            <input type="number" id="days-input" class="input-box" value="30" />
            <div class="input-tip">标准月度授权为 30 天。</div>
          </div>

          <button id="btn-issue" class="btn-issue" onclick="issueLicense()">
            确认发码
          </button>

          <div id="result-box" class="lic-result">
            <strong style="color: #34d399;">🎉 授权码已签发！请复制发给客户：</strong>
            <div id="result-lic" class="lic-text"></div>
            <button class="btn-copy" onclick="copyResult()">📋 复制授权码与激活指引</button>
          </div>
        </div>

        <div class="card">
          <h2>📜 代理商权益与商业指南</h2>
          <div style="font-size: 13px; color: #cbd5e1; line-height: 1.7;">
            <p><strong>1. 自主定价与全额收款：</strong><br>
            您可以向终端卖家自由定价（推荐 600 元/月），客户资金直接打入您的微信/支付宝账户，差价利润全归您所有。</p>
            <br>
            <p><strong>2. 阶梯批发计费规则：</strong><br>
            • <strong>0 ~ 100 家店铺</strong>：出厂价固定 <strong>¥240.00 / 店铺</strong>；<br>
            • <strong>101 家店铺起</strong>：系统自动跳档至 <strong>¥180.00 / 店铺</strong>。</p>
            <br>
            <p><strong>3. 预存余额充值：</strong><br>
            如预存余额不足，请联系总管理员为您充值额度。</p>
          </div>
        </div>
      </div>

      <div class="card">
        <h2>📋 最近发出的授权卡片记录</h2>
        <div style="overflow-x:auto;">
          <table>
            <thead>
              <tr>
                <th>客户 / 店铺名称</th>
                <th>会话 ID / 机器码</th>
                <th>专属授权码 (License Key)</th>
                <th>有效期至</th>
                <th>发码时间</th>
              </tr>
            </thead>
            <tbody id="issued-table-body">
              <tr><td colspan="5" style="text-align:center;color:#64748b;">正在加载发码记录...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div id="pwd-modal" class="modal-overlay">
    <div class="modal-card">
      <h3 style="color:#fff;margin-bottom:16px;">🔑 修改登录密码</h3>
      <div class="form-group">
        <label>原密码</label>
        <input type="password" id="old-pwd-input" class="input-box" placeholder="请输入原密码" />
      </div>
      <div class="form-group">
        <label>新密码 (至少 6 位)</label>
        <input type="password" id="new-pwd-input" class="input-box" placeholder="请输入新密码" />
      </div>
      <div style="display:flex;gap:8px;margin-top:20px;">
        <button class="btn-primary" style="flex:1;" onclick="doChangePassword()">确认修改</button>
        <button class="btn-sm" style="flex:1;" onclick="closeChangePwdModal()">取消</button>
      </div>
    </div>
  </div>

  <div id="recharge-modal" class="modal-overlay">
    <div class="modal-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="color:#fff;margin:0;">💳 代理商预存额度充值</h3>
        <span style="color:#94a3b8;cursor:pointer;font-size:20px;line-height:1;" onclick="closeRechargeModal()">✕</span>
      </div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:16px;">
        选择预存档位或输入自定义金额，扫码付款后<strong>资金直达总管理员支付宝，预存余额秒级自动到账</strong>。
      </div>
      
      <div class="preset-grid">
        <div class="preset-btn active" data-amt="2400" onclick="selectPreset(this, 2400)">
          <div style="font-weight:700;font-size:16px;color:#fff;">¥2,400</div>
          <div style="font-size:11px;color:#94a3b8;">可发 10 店 (¥240/店)</div>
        </div>
        <div class="preset-btn" data-amt="4800" onclick="selectPreset(this, 4800)">
          <div style="font-weight:700;font-size:16px;color:#fff;">¥4,800</div>
          <div style="font-size:11px;color:#94a3b8;">可发 20 店 (推荐)</div>
        </div>
        <div class="preset-btn" data-amt="12000" onclick="selectPreset(this, 12000)">
          <div style="font-weight:700;font-size:16px;color:#fff;">¥12,000</div>
          <div style="font-size:11px;color:#94a3b8;">可发 50 店 (畅销)</div>
        </div>
        <div class="preset-btn" data-amt="18000" onclick="selectPreset(this, 18000)">
          <div style="font-weight:700;font-size:16px;color:#34d399;">¥18,000</div>
          <div style="font-size:11px;color:#34d399;">冲 100 店特惠档</div>
        </div>
      </div>

      <div class="form-group">
        <label>自定义充值金额 (元)</label>
        <input type="number" id="custom-amt-input" class="input-box" value="2400" min="1" oninput="onCustomAmtChange()" />
      </div>

      <div style="display:flex;gap:8px;margin-top:20px;">
        <button id="btn-do-recharge" class="btn-primary" style="flex:1;background:#059669;" onclick="doRecharge()">前往支付宝安全支付 / 扫码</button>
        <button class="btn-sm" style="flex:0.35;" onclick="closeRechargeModal()">取消</button>
      </div>
    </div>
  </div>

  <script>
    var currentToken = "${queryToken}" || localStorage.getItem("agent_token") || "";
    var currentAgent = null;
    var generatedKey = "";
    var selectedRechargeAmt = 2400;

    function copyText(str) {
      if (!str) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(str).then(function() {
          alert("✅ 复制成功！");
        }).catch(function() {
          prompt("请手动选择复制：", str);
        });
      } else {
        prompt("请手动选择复制：", str);
      }
    }

    async function init() {
      if (currentToken) {
        var ok = await loadDashboard();
        if (ok) {
          var urlParams = new URLSearchParams(window.location.search);
          var rechId = urlParams.get('recharge_order_id');
          if (rechId) {
            pollRechargeStatus(rechId, 0);
          }
          return;
        }
      }
      showLogin();
    }

    function showLogin() {
      document.getElementById('login-section').style.display = 'block';
      document.getElementById('dashboard-section').style.display = 'none';
    }

    function showDashboard() {
      document.getElementById('login-section').style.display = 'none';
      document.getElementById('dashboard-section').style.display = 'block';
    }

    async function doLogin() {
      var u = document.getElementById('login-username').value.trim();
      var p = document.getElementById('login-password').value;
      var errDiv = document.getElementById('login-error');
      errDiv.style.display = 'none';

      if (!u || !p) {
        errDiv.innerText = '请输入用户名与密码';
        errDiv.style.display = 'block';
        return;
      }

      try {
        var res = await fetch('/api/agent/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: u, password: p })
        });
        var data = await res.json();
        if (!data.ok) {
          errDiv.innerText = data.error || '登录失败';
          errDiv.style.display = 'block';
          return;
        }
        currentToken = data.token;
        localStorage.setItem("agent_token", currentToken);
        await loadDashboard();
      } catch (e) {
        errDiv.innerText = '请求异常: ' + e.message;
        errDiv.style.display = 'block';
      }
    }

    async function loadDashboard() {
      try {
        var res = await fetch('/api/agent/info?token=' + encodeURIComponent(currentToken));
        var data = await res.json();
        if (!data.ok) {
          localStorage.removeItem("agent_token");
          currentToken = "";
          return false;
        }
        currentAgent = data.agent;
        renderDashboard(data.agent, data.licenses || []);
        showDashboard();
        return true;
      } catch (e) {
        return false;
      }
    }

    function renderDashboard(ag, licenses) {
      document.getElementById('agent-tag-name').innerText = '🏢 ' + ag.name + ' (' + ag.username + ')';
      document.getElementById('stat-balance').innerText = '¥' + ag.balance.toFixed(2);
      document.getElementById('stat-issued').innerHTML = ag.total_stores_issued + ' <small style="font-size:14px;color:#94a3b8;">家</small>';
      document.getElementById('stat-tier').innerHTML = '¥' + ag.tier_price.toFixed(2) + ' <small style="font-size:14px;color:#94a3b8;">/ 店</small>';
      document.getElementById('stat-tier-desc').innerText = ag.total_stores_issued < 100 ? '0-100家档 (¥240/店)' : '101+家大代理档 (¥180/店)';

      document.getElementById('tier-issued-count').innerText = ag.total_stores_issued;
      var percent = Math.min(100, Math.round((ag.total_stores_issued / 100) * 100));
      document.getElementById('tier-progress-bar').style.width = percent + '%';
      if (ag.total_stores_issued >= 100) {
        document.getElementById('tier-tip').innerHTML = '🎉 已晋升特惠档：永久享受 <span style="color:#10b981;">¥180/店</span> 出厂价！';
      } else {
        document.getElementById('tier-tip').innerText = '还需开通 ' + (100 - ag.total_stores_issued) + ' 家即可享 ¥180/店 特惠出厂价！';
      }

      document.getElementById('btn-issue').innerText = '确认发码 (扣除出厂价 ¥' + ag.tier_price.toFixed(2) + ')';

      var tbody = document.getElementById('issued-table-body');
      if (!licenses || !licenses.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:20px;">暂无发码记录，点击上方发码开始拓展客户</td></tr>';
      } else {
        tbody.innerHTML = licenses.map(function(lic) {
          var name = lic.name || '客户';
          var store = lic.store_name || '-';
          var mid = lic.machine_id || '-';
          var exp = lic.expires_at || '-';
          var cat = (lic.created_at || '').substring(0, 16).replace('T', ' ');
          return '<tr>' +
            '<td><strong>' + name + '</strong><br><small style="color:#6366f1;">🏪 ' + store + '</small></td>' +
            '<td><code>' + mid + '</code></td>' +
            '<td style="font-family:monospace;font-size:11px;word-break:break-all;max-width:280px;">' + lic.key + '</td>' +
            '<td>' + exp + '</td>' +
            '<td><small style="color:#64748b;">' + cat + '</small></td>' +
            '</tr>';
        }).join('');
      }
    }

    async function issueLicense() {
      var mid = document.getElementById('mid-input').value.trim();
      var storeName = document.getElementById('store-input').value.trim();
      var customer = document.getElementById('customer-input').value.trim();
      var days = parseInt(document.getElementById('days-input').value) || 30;

      if (!mid) { alert('请输入客户会话 ID 或机器码！'); return; }
      if (!storeName) { alert('请输入客户店铺名称！'); return; }

      var btn = document.getElementById('btn-issue');
      btn.disabled = true;
      btn.innerText = '正在生成 RSA 防伪授权码...';

      try {
        var res = await fetch('/api/agent/issue-license', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: currentToken,
            mid: mid,
            store_name: storeName,
            customer_name: customer,
            days: days
          })
        });
        var data = await res.json();
        if (!data.ok) {
          alert('发码失败: ' + (data.error || '未知错误'));
          btn.disabled = false;
          btn.innerText = '确认发码';
          return;
        }

        generatedKey = data.license_key;
        document.getElementById('result-box').style.display = 'block';
        document.getElementById('result-lic').innerText = data.license_key;
        btn.disabled = false;
        btn.innerText = '发码成功！可继续发下一张';
        loadDashboard();
      } catch (e) {
        alert('请求异常: ' + e.message);
        btn.disabled = false;
        btn.innerText = '确认发码';
      }
    }

    function copyResult() {
      var text = '【Wildberries 极速搬家上架助手】您的专属店铺授权码：\\n' + generatedKey + '\\n\\n👉 激活方法：在 Antigravity 聊天框中发送：\\n激活授权 ' + generatedKey;
      copyText(text);
    }

    function openChangePwdModal() {
      document.getElementById('pwd-modal').style.display = 'flex';
    }
    function closeChangePwdModal() {
      document.getElementById('pwd-modal').style.display = 'none';
    }

    async function doChangePassword() {
      var oldPwd = document.getElementById('old-pwd-input').value;
      var newPwd = document.getElementById('new-pwd-input').value;
      if (!newPwd || newPwd.length < 6) {
        alert('新密码长度不能少于 6 位');
        return;
      }
      try {
        var res = await fetch('/api/agent/change-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: currentToken, old_password: oldPwd, new_password: newPwd })
        });
        var data = await res.json();
        if (data.ok) {
          alert('✅ 密码修改成功！');
          closeChangePwdModal();
        } else {
          alert('修改失败: ' + data.error);
        }
      } catch (e) {
        alert('请求异常: ' + e.message);
      }
    }

    function openRechargeModal() {
      document.getElementById('recharge-modal').style.display = 'flex';
      selectPreset(document.querySelector('.preset-btn[data-amt="2400"]'), 2400);
    }
    function closeRechargeModal() {
      document.getElementById('recharge-modal').style.display = 'none';
    }
    function selectPreset(el, amt) {
      selectedRechargeAmt = amt;
      document.querySelectorAll('.preset-btn').forEach(function(b) { b.classList.remove('active'); });
      if (el) el.classList.add('active');
      document.getElementById('custom-amt-input').value = amt;
    }
    function onCustomAmtChange() {
      var val = parseFloat(document.getElementById('custom-amt-input').value) || 0;
      selectedRechargeAmt = val;
      document.querySelectorAll('.preset-btn').forEach(function(b) {
        if (parseFloat(b.dataset.amt) === val) b.classList.add('active');
        else b.classList.remove('active');
      });
    }

    async function doRecharge() {
      var amt = parseFloat(document.getElementById('custom-amt-input').value) || selectedRechargeAmt;
      if (isNaN(amt) || amt <= 0) {
        alert('请输入有效的充值金额！');
        return;
      }
      var btn = document.getElementById('btn-do-recharge');
      btn.disabled = true;
      btn.innerText = '正在生成支付宝收银台...';

      try {
        var res = await fetch('/api/agent/create-recharge-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: currentToken, amount: amt })
        });
        var data = await res.json();
        if (!data.ok) {
          alert('创建充值订单失败: ' + (data.error || '未知错误'));
          btn.disabled = false;
          btn.innerText = '前往支付宝安全支付 / 扫码';
          return;
        }

        window.open(data.pay_url, '_blank');
        btn.innerText = '正在等待支付宝支付完成...';
        pollRechargeStatus(data.order_id, amt);
      } catch (e) {
        alert('请求异常: ' + e.message);
        btn.disabled = false;
        btn.innerText = '前往支付宝安全支付 / 扫码';
      }
    }

    async function pollRechargeStatus(orderId, amt) {
      try {
        var res = await fetch('/api/agent/recharge-status?order_id=' + encodeURIComponent(orderId) + '&token=' + encodeURIComponent(currentToken));
        var data = await res.json();
        if (data.ok && data.status === 'PAID') {
          alert('🎉 支付宝充值到账成功！\\n充值金额：¥' + (amt ? amt.toFixed(2) : (data.amount || '')) + '\\n当前最新账户余额：¥' + (data.new_balance !== null ? Number(data.new_balance).toFixed(2) : ''));
          closeRechargeModal();
          var btn = document.getElementById('btn-do-recharge');
          if (btn) {
            btn.disabled = false;
            btn.innerText = '前往支付宝安全支付 / 扫码';
          }
          loadDashboard();
        } else {
          setTimeout(function() { pollRechargeStatus(orderId, amt); }, 2500);
        }
      } catch (e) {
        setTimeout(function() { pollRechargeStatus(orderId, amt); }, 3500);
      }
    }

    function doLogout() {
      localStorage.removeItem("agent_token");
      currentToken = "";
      showLogin();
    }

    init();
  </script>
</body>
</html>`;

      return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
    }

    // 5.5 Agent Dispense API: POST /api/agent/issue-license
    if (path === "/api/agent/issue-license" && method === "POST") {
      try {
        const body = await request.json();
        const { token, mid, store_name, customer_name, days = 30 } = body;

        if (!token) return new Response(JSON.stringify({ ok: false, error: "缺少代理商 Token" }), { status: 401, headers: corsHeaders });
        if (!mid) return new Response(JSON.stringify({ ok: false, error: "缺少客户会话 ID 或机器码" }), { status: 400, headers: corsHeaders });
        if (!store_name) return new Response(JSON.stringify({ ok: false, error: "缺少店铺名称" }), { status: 400, headers: corsHeaders });

        if (!env.WB_LICENSES) {
          return new Response(JSON.stringify({ ok: false, error: "KV 未绑定" }), { status: 500, headers: corsHeaders });
        }

        const found = await findAgentByToken(token);
        if (!found) {
          return new Response(JSON.stringify({ ok: false, error: "无效的代理商凭证或登录已过期" }), { status: 403, headers: corsHeaders });
        }
        const agent = found.data;
        const agentKey = found.key;

        if (agent.status === "FROZEN") {
          return new Response(JSON.stringify({ ok: false, error: "该代理商账户已被冻结，无法发码" }), { status: 403, headers: corsHeaders });
        }

        const totalIssued = Number(agent.total_stores_issued || 0);
        const costPrice = getAgentTierPrice(totalIssued);
        const curBalance = Number(agent.balance || 0);

        if (curBalance < costPrice) {
          return new Response(JSON.stringify({
            ok: false,
            error: `预存余额不足 (当前: ¥${curBalance.toFixed(2)}, 本单出厂价: ¥${costPrice.toFixed(2)})，请联系管理员充值。`
          }), { status: 400, headers: corsHeaders });
        }

        // Sign RSA license
        const targetMid = mid.trim().toUpperCase();
        const clientName = (customer_name || store_name || "代理商客户").trim();
        const cleanStore = store_name.trim();
        const { license_key, payload } = signLicenseKey(targetMid, clientName, cleanStore, Number(days), 1, rsaSignKeyB64);

        // Deduct balance and increment issued count
        agent.balance = Number((curBalance - costPrice).toFixed(2));
        agent.total_stores_issued = totalIssued + 1;
        agent.last_issued_at = new Date().toISOString();
        await env.WB_LICENSES.put(agentKey, JSON.stringify(agent));

        // Save license to KV
        const licKvKey = getLicenseKvKey(license_key);
        const licRecord = {
          key: license_key,
          name: clientName,
          store_name: cleanStore,
          machine_id: targetMid,
          max_sessions: 1,
          expires_at: payload.exp,
          type: "RSA-PSS-SHA256",
          created_at: new Date().toISOString(),
          source: `AGENT:${agent.agent_id}`,
          agent_name: agent.name,
          cost_price: costPrice,
          activated_sessions: []
        };
        await env.WB_LICENSES.put(licKvKey, JSON.stringify(licRecord));

        return new Response(JSON.stringify({
          ok: true,
          license_key: license_key,
          cost_price: costPrice,
          new_balance: agent.balance,
          total_stores_issued: agent.total_stores_issued,
          expires_at: payload.exp,
          store_name: cleanStore
        }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
      } catch (err) {
        return new Response(JSON.stringify({ ok: false, error: err.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 5.6 Agent Recharge Order API: POST /api/agent/create-recharge-order
    if (path === "/api/agent/create-recharge-order" && method === "POST") {
      try {
        const { token, amount } = await request.json();
        if (!token) return new Response(JSON.stringify({ ok: false, error: "缺少代理商凭证 Token" }), { status: 401, headers: corsHeaders });
        
        const numAmount = parseFloat(amount);
        if (isNaN(numAmount) || numAmount <= 0) {
          return new Response(JSON.stringify({ ok: false, error: "充值金额必须大于 0 元" }), { status: 400, headers: corsHeaders });
        }

        const found = await findAgentByToken(token);
        if (!found) {
          return new Response(JSON.stringify({ ok: false, error: "无效的代理商凭证或登录已过期" }), { status: 403, headers: corsHeaders });
        }
        const agent = found.data;

        const orderId = `ORD_AGTRECH_${Date.now()}_${Math.random().toString(36).substring(2, 6).toUpperCase()}`;
        const amountStr = numAmount.toFixed(2);
        const returnUrl = `${url.origin}/agent?recharge_order_id=${orderId}`;
        const notifyUrl = `${url.origin}/api/pay/alipay-callback`;

        const passbackObj = {
          type: "AGENT_RECHARGE",
          agent_id: agent.agent_id,
          amount: amountStr
        };

        const bizContent = {
          out_trade_no: orderId,
          total_amount: amountStr,
          subject: `Wildberries代理商额度充值-${agent.name}`,
          product_code: "FAST_INSTANT_TRADE_PAY",
          body: JSON.stringify(passbackObj),
          passback_params: encodeURIComponent(JSON.stringify(passbackObj))
        };

        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const nowFormat = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

        const params = {
          app_id: alipayAppId,
          method: "alipay.trade.page.pay",
          format: "JSON",
          return_url: returnUrl,
          notify_url: notifyUrl,
          charset: "utf-8",
          sign_type: "RSA2",
          timestamp: nowFormat,
          version: "1.0",
          biz_content: JSON.stringify(bizContent)
        };

        const sign = signAlipayParams(params, alipayPrivKey);
        params.sign = sign;

        const queryStr = Object.keys(params).map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`).join('&');
        const payUrl = `https://openapi.alipay.com/gateway.do?${queryStr}`;

        // Save Pending Order into KV
        if (env.WB_LICENSES) {
          const orderRecord = {
            order_id: orderId,
            type: "AGENT_RECHARGE",
            status: "PENDING",
            agent_id: agent.agent_id,
            agent_name: agent.name,
            amount: amountStr,
            plan_name: `代理商充值 (¥${amountStr})`,
            created_at: nowFormat
          };
          await env.WB_LICENSES.put(`ORD:${orderId}`, JSON.stringify(orderRecord), { expirationTtl: 86400 * 7 });
        }

        return new Response(JSON.stringify({
          ok: true,
          order_id: orderId,
          amount: amountStr,
          pay_url: payUrl
        }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
      } catch (err) {
        return new Response(JSON.stringify({ ok: false, error: err.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 5.7 Agent Recharge Status Query API: GET /api/agent/recharge-status
    if (path === "/api/agent/recharge-status" && method === "GET") {
      const orderId = url.searchParams.get("order_id");
      const token = url.searchParams.get("token");
      if (!orderId || !env.WB_LICENSES) {
        return new Response(JSON.stringify({ ok: false, error: "Missing order_id" }), { status: 400, headers: corsHeaders });
      }

      const ordJson = await env.WB_LICENSES.get(`ORD:${orderId}`);
      if (!ordJson) {
        return new Response(JSON.stringify({ ok: false, status: "NOT_FOUND" }), { status: 404, headers: corsHeaders });
      }

      const ord = JSON.parse(ordJson);
      let newBalance = null;
      if (token) {
        const found = await findAgentByToken(token);
        if (found) newBalance = found.data.balance;
      }

      return new Response(JSON.stringify({
        ok: true,
        status: ord.status,
        amount: ord.amount,
        new_balance: newBalance,
        paid_at: ord.paid_at || ""
      }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    // ==========================================
    // 6. Super Admin Auth, Dashboard & Operations
    // ==========================================

    async function getAdminCredentials(env) {
      let username = env.ADMIN_USERNAME || "admin";
      let password = env.ADMIN_PASSWORD || env.ADMIN_SECRET || "";
      if (env.WB_LICENSES) {
        const raw = await env.WB_LICENSES.get("ADMIN_CONFIG");
        if (raw) {
          try {
            const cfg = JSON.parse(raw);
            if (cfg.username) username = cfg.username;
            if (cfg.password) password = cfg.password;
          } catch (e) {}
        }
      }
      return { username, password };
    }

    async function verifyAdminAuth(request, env, url) {
      const adminSecret = env.ADMIN_SECRET || "";
      
      const keyParam = url.searchParams.get("key");
      const headerSecret = request.headers.get("X-Admin-Secret");
      if ((keyParam && keyParam === adminSecret) || (headerSecret && headerSecret === adminSecret)) {
        return { isAuth: true, username: "admin" };
      }

      let token = url.searchParams.get("token") || request.headers.get("X-Admin-Token");
      if (!token) {
        const authHeader = request.headers.get("Authorization") || "";
        if (authHeader.startsWith("Bearer ")) token = authHeader.substring(7);
      }

      if (token) {
        if (token === adminSecret) return { isAuth: true, username: "admin" };
        if (env.WB_LICENSES) {
          const sess = await env.WB_LICENSES.get(`ADMIN_SESSION:${token}`);
          if (sess) {
            try {
              const data = JSON.parse(sess);
              return { isAuth: true, username: data.username || "admin" };
            } catch (e) {
              return { isAuth: true, username: "admin" };
            }
          }
        }
      }

      return { isAuth: false };
    }

    // 6.1 Super Admin Login API: POST /admin/api/login
    if (path === "/admin/api/login" && method === "POST") {
      try {
        const { username, password } = await request.json();
        if (!username || !password) {
          return new Response(JSON.stringify({ ok: false, error: "请输入超级管理员用户名与密码" }), { status: 400, headers: corsHeaders });
        }
        const creds = await getAdminCredentials(env);
        if (username.trim() !== creds.username || password !== creds.password) {
          return new Response(JSON.stringify({ ok: false, error: "超级管理员账号或密码错误" }), { status: 401, headers: corsHeaders });
        }

        const sessionToken = `ADM-SEC-${crypto.randomUUID().replace(/-/g, '')}`;
        if (env.WB_LICENSES) {
          await env.WB_LICENSES.put(`ADMIN_SESSION:${sessionToken}`, JSON.stringify({
            username: creds.username,
            login_at: new Date().toISOString()
          }), { expirationTtl: 86400 * 7 });
        }

        return new Response(JSON.stringify({
          ok: true,
          token: sessionToken,
          username: creds.username
        }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 6.2 Super Admin Change Password API: POST /admin/api/change-password
    if (path === "/admin/api/change-password" && method === "POST") {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      try {
        const { old_password, new_username, new_password } = await request.json();
        const creds = await getAdminCredentials(env);
        if (old_password && old_password !== creds.password) {
          return new Response(JSON.stringify({ ok: false, error: "原管理员密码不正确" }), { status: 400, headers: corsHeaders });
        }
        if (new_password && new_password.length < 6) {
          return new Response(JSON.stringify({ ok: false, error: "新密码长度至少需要 6 位" }), { status: 400, headers: corsHeaders });
        }

        const newConfig = {
          username: (new_username && new_username.trim()) ? new_username.trim() : creds.username,
          password: (new_password && new_password.trim()) ? new_password.trim() : creds.password,
          updated_at: new Date().toISOString()
        };

        if (env.WB_LICENSES) {
          await env.WB_LICENSES.put("ADMIN_CONFIG", JSON.stringify(newConfig));
        }

        return new Response(JSON.stringify({ ok: true, message: "超级管理员账号密码修改成功！", username: newConfig.username }), {
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 6.3 Super Admin Data API: GET /admin/api/data
    if (path === "/admin/api/data" && (method === "GET" || method === "POST")) {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });

      const listRes = await env.WB_LICENSES.list();
      const licenses = [];
      const orders = [];
      const agents = [];

      for (const k of listRes.keys) {
        const val = await env.WB_LICENSES.get(k.name);
        try {
          const parsed = JSON.parse(val);
          if (k.name.startsWith("ORD:")) {
            orders.push(parsed);
          } else if (k.name.startsWith("AGENT:")) {
            agents.push({ key: k.name, ...parsed });
          } else if (k.name.startsWith("AGENT_USER:") || k.name.startsWith("AGENT_TOKEN:") || k.name.startsWith("ADMIN_SESSION:") || k.name === "ADMIN_CONFIG") {
            // internal
          } else {
            licenses.push({ key: parsed.key || k.name, ...parsed });
          }
        } catch (e) {
          licenses.push({ key: k.name, raw: val });
        }
      }

      orders.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
      agents.sort((a, b) => (b.total_stores_issued || 0) - (a.total_stores_issued || 0));

      return new Response(JSON.stringify({
        ok: true,
        admin_user: auth.username,
        licenses,
        orders,
        agents
      }), { headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    // 6.4 Super Admin Web Dashboard: GET /admin
    if (path === "/admin" && method === "GET") {
      const queryKey = url.searchParams.get("key") || "";
      const queryToken = url.searchParams.get("token") || "";

      const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>超级管理员控制台 · Wildberries 商业授权与代理商财务系统</title>
  <style>
    :root {
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --accent-green: #10b981;
      --accent-red: #ef4444;
      --accent-blue: #38bdf8;
      --accent-purple: #8b5cf6;
      --text: #f8fafc;
      --text-sub: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #1e293b; padding: 24px; margin: 0; min-height: 100vh; }
    
    #admin-login-screen {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 80vh;
    }
    .login-card {
      background: #0f172a;
      color: #f8fafc;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 36px 32px;
      width: 100%;
      max-width: 420px;
      box-shadow: 0 20px 25px -5px rgba(0,0,0,0.3);
    }
    .login-title { font-size: 20px; font-weight: 700; text-align: center; margin-bottom: 8px; color: #fff; }
    .login-sub { font-size: 13px; color: #94a3b8; text-align: center; margin-bottom: 24px; }
    
    .form-group { margin-bottom: 16px; }
    label { display: block; font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; }
    .input-box { width: 100%; background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; color: #fff; font-size: 14px; outline: none; }
    .input-box:focus { border-color: #6366f1; }
    .btn-login { width: 100%; background: #6366f1; color: #fff; border: none; border-radius: 8px; padding: 12px; font-size: 14px; font-weight: 700; cursor: pointer; transition: 0.2s; }
    .btn-login:hover { background: #4f46e5; }
    .login-err { color: #f87171; font-size: 12px; margin-top: 12px; text-align: center; display: none; }

    #admin-dashboard-screen { display: none; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 16px; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
    h1 { font-size: 20px; font-weight: 700; color: #0f172a; margin: 0; }
    .stats-bar { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    .stat-card { background: #fff; padding: 16px 20px; border-radius: 8px; border: 1px solid #e2e8f0; flex: 1; min-width: 180px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .stat-num { font-size: 24px; font-weight: 700; color: #0f172a; margin-top: 4px; }
    .stat-label { font-size: 12px; color: #64748b; font-weight: 600; }
    
    .nav-tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
    .tab-btn { padding: 8px 16px; border-radius: 6px; border: 1px solid #cbd5e1; background: #fff; font-size: 13px; font-weight: 600; cursor: pointer; }
    .tab-btn.active { background: #6366f1; color: #fff; border-color: #6366f1; }

    .badge { padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .badge-active { background: #dcfce7; color: #166534; }
    .badge-banned { background: #fee2e2; color: #991b1b; }
    .badge-paid { background: #dbeafe; color: #1e40af; }
    .badge-pending { background: #fef3c7; color: #92400e; }

    table { width: 100%; border-collapse: collapse; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 32px; }
    th, td { padding: 12px 16px; text-align: left; font-size: 13px; border-bottom: 1px solid #f1f5f9; }
    th { background: #f1f5f9; font-weight: 600; color: #475569; }
    tr:hover { background: #f8fafc; }
    button.action-btn { padding: 6px 12px; border-radius: 6px; border: none; font-size: 12px; font-weight: 500; cursor: pointer; transition: 0.15s; }
    .btn-ban { background: #ef4444; color: white; }
    .btn-ban:hover { background: #dc2626; }
    .btn-unban { background: #10b981; color: white; }
    .btn-unban:hover { background: #059669; }
    .btn-renew { background: #3b82f6; color: white; margin-left: 4px; }
    .btn-renew:hover { background: #2563eb; }
    .btn-pwd { background: #8b5cf6; color: white; margin-left: 4px; }
    .btn-pwd:hover { background: #7c3aed; }
    .btn-create { background: #6366f1; color: #fff; padding: 8px 16px; border-radius: 6px; border: none; font-size: 13px; font-weight: 600; cursor: pointer; }
    .btn-create:hover { background: #4f46e5; }
    .btn-sm-header { padding: 8px 14px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; text-decoration: none; border: 1px solid #cbd5e1; background: #fff; color: #1e293b; }
    .btn-sm-header:hover { background: #f1f5f9; }
    .btn-logout { color: #dc2626; border-color: #fca5a5; background: #fef2f2; }
    .btn-logout:hover { background: #fee2e2; }
    .key-cell { font-family: monospace; font-size: 11px; word-break: break-all; max-width: 260px; }
    .copy-link { color: #6366f1; font-size: 12px; text-decoration: none; cursor: pointer; margin-left: 4px; }

    .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px); z-index: 999; align-items: center; justify-content: center; }
    .modal-card { background: #fff; border-radius: 12px; padding: 24px; width: 100%; max-width: 440px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.3); }
    .modal-card label { color: #334155; }
    .modal-card .input-box { background: #f8fafc; border-color: #cbd5e1; color: #0f172a; }
  </style>
</head>
<body>
  
  <div id="admin-login-screen">
    <div class="login-card">
      <div class="login-title">🛡️ 超级管理员控制台 · 登录</div>
      <div class="login-sub">Wildberries 跨境搬家 · 全局商业授权与财务系统</div>
      
      <div class="form-group">
        <label>👑 管理员账号 (Username)</label>
        <input type="text" id="adm-user-input" class="input-box" placeholder="请输入管理员用户名 (默认 admin)" />
      </div>
      <div class="form-group">
        <label>🔑 登录密码 (Password)</label>
        <input type="password" id="adm-pass-input" class="input-box" placeholder="请输入管理员密码" />
      </div>
      <button class="btn-login" onclick="doAdminLogin()">安全登录总控制台</button>
      <div id="adm-login-err" class="login-err"></div>
    </div>
  </div>

  <div id="admin-dashboard-screen">
    <div class="header">
      <div>
        <h1>🛡️ Wildberries 商业授权与代理商财务控制台</h1>
        <div style="font-size:12px;color:#64748b;margin-top:4px;">当前登录管理员：<strong id="logged-admin-user" style="color:#6366f1;">admin</strong></div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <button class="btn-create" onclick="openCreateAgentModal()">➕ 创建新代理商</button>
        <button class="btn-sm-header" onclick="openChangeAdminPwdModal()">🔑 修改超管密码</button>
        <a href="/agent" target="_blank" style="padding: 8px 14px; background: #4f46e5; color: #fff; text-decoration: none; border-radius: 6px; font-size: 13px; font-weight: 600;">🤝 代理商入口</a>
        <a href="/pay" target="_blank" style="padding: 8px 14px; background: #1677ff; color: #fff; text-decoration: none; border-radius: 6px; font-size: 13px; font-weight: 600;">🛒 收银台</a>
        <button class="btn-sm-header btn-logout" onclick="doAdminLogout()">🚪 退出登录</button>
      </div>
    </div>

    <div class="stats-bar">
      <div class="stat-card">
        <div class="stat-label">总授权店铺数</div>
        <div class="stat-num" id="stat-total-licenses">0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">🤝 合作代理商数</div>
        <div class="stat-num" id="stat-total-agents" style="color: #6366f1;">0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">支付宝成交订单</div>
        <div class="stat-num" id="stat-total-orders" style="color: #3b82f6;">0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累计直营交易流水</div>
        <div class="stat-num" id="stat-total-revenue" style="color: #8b5cf6;">¥0.00</div>
      </div>
    </div>

    <div class="nav-tabs">
      <button class="tab-btn active" onclick="switchTab('agents')">🤝 代理商体系 (<span id="tab-cnt-agents">0</span>)</button>
      <button class="tab-btn" onclick="switchTab('licenses')">🔑 店铺授权列表 (<span id="tab-cnt-licenses">0</span>)</button>
      <button class="tab-btn" onclick="switchTab('orders')">💳 直营支付订单 (<span id="tab-cnt-orders">0</span>)</button>
    </div>

    <div id="tab-agents">
      <table>
        <thead>
          <tr>
            <th>代理商名称</th>
            <th>登录账号 (Username)</th>
            <th>登录密码 (Password)</th>
            <th>预存余额 (元)</th>
            <th>累计开通数</th>
            <th>当前出厂价</th>
            <th>状态</th>
            <th>管理操作</th>
          </tr>
        </thead>
        <tbody id="agent-table-body">
          <tr><td colspan="8" style="text-align:center;padding:20px;color:#64748b;">正在加载代理商列表...</td></tr>
        </tbody>
      </table>
    </div>

    <div id="tab-licenses" style="display: none;">
      <table>
        <thead>
          <tr>
            <th>客户 / 店铺名称</th>
            <th>绑定机器码 / 会话 ID</th>
            <th>授权码 (License Key)</th>
            <th>授权有效期</th>
            <th>累积用量</th>
            <th>来源渠道</th>
            <th>状态</th>
            <th>管理操作</th>
          </tr>
        </thead>
        <tbody id="license-table-body">
          <tr><td colspan="8" style="text-align:center;padding:20px;color:#64748b;">正在加载店铺授权列表...</td></tr>
        </tbody>
      </table>
    </div>

    <div id="tab-orders" style="display: none;">
      <table>
        <thead>
          <tr>
            <th>商户订单号</th>
            <th>授权套餐</th>
            <th>店铺简称</th>
            <th>实付金额</th>
            <th>客户名称</th>
            <th>绑定机器码</th>
            <th>支付宝流水号</th>
            <th>支付时间</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody id="order-table-body">
          <tr><td colspan="9" style="text-align:center;padding:20px;color:#64748b;">正在加载直营订单...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div id="admin-pwd-modal" class="modal-overlay">
    <div class="modal-card">
      <h3 style="color:#0f172a;margin-bottom:16px;">🔑 修改超级管理员账号与密码</h3>
      <div class="form-group">
        <label>原密码 <span style="color:#ef4444;">*</span></label>
        <input type="password" id="adm-old-pwd" class="input-box" placeholder="请输入原管理员密码" />
      </div>
      <div class="form-group">
        <label>新管理员用户名 (如需修改)</label>
        <input type="text" id="adm-new-user" class="input-box" placeholder="留空则保持当前用户名" />
      </div>
      <div class="form-group">
        <label>新管理员密码 (至少 6 位) <span style="color:#ef4444;">*</span></label>
        <input type="password" id="adm-new-pwd" class="input-box" placeholder="请输入新密码" />
      </div>
      <div style="display:flex;gap:8px;margin-top:20px;">
        <button class="btn-create" style="flex:1;" onclick="doChangeAdminPwd()">确认更新密码</button>
        <button class="btn-sm-header" style="flex:1;" onclick="closeChangeAdminPwdModal()">取消</button>
      </div>
    </div>
  </div>

  <script>
    var adminToken = "${queryToken}" || "${queryKey}" || localStorage.getItem("wb_admin_token") || "";

    function copyText(str) {
      if (!str) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(str).then(function() {
          alert("✅ 复制成功！");
        }).catch(function() {
          prompt("请手动选择复制：", str);
        });
      } else {
        prompt("请手动选择复制：", str);
      }
    }

    function switchTab(tab) {
      document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
      document.getElementById('tab-agents').style.display = tab === 'agents' ? 'block' : 'none';
      document.getElementById('tab-licenses').style.display = tab === 'licenses' ? 'block' : 'none';
      document.getElementById('tab-orders').style.display = tab === 'orders' ? 'block' : 'none';
      event.target.classList.add('active');
    }

    async function init() {
      if (adminToken) {
        var ok = await loadDashboard();
        if (ok) return;
      }
      showLogin();
    }

    function showLogin() {
      document.getElementById('admin-login-screen').style.display = 'flex';
      document.getElementById('admin-dashboard-screen').style.display = 'none';
    }

    function showDashboard() {
      document.getElementById('admin-login-screen').style.display = 'none';
      document.getElementById('admin-dashboard-screen').style.display = 'block';
    }

    async function doAdminLogin() {
      var u = document.getElementById('adm-user-input').value.trim();
      var p = document.getElementById('adm-pass-input').value;
      var errDiv = document.getElementById('adm-login-err');
      errDiv.style.display = 'none';

      if (!u || !p) {
        errDiv.innerText = '请输入用户名与密码';
        errDiv.style.display = 'block';
        return;
      }

      try {
        var res = await fetch('/admin/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: u, password: p })
        });
        var data = await res.json();
        if (!data.ok) {
          errDiv.innerText = data.error || '登录失败';
          errDiv.style.display = 'block';
          return;
        }
        adminToken = data.token;
        localStorage.setItem("wb_admin_token", adminToken);
        await loadDashboard();
      } catch (e) {
        errDiv.innerText = '请求异常: ' + e.message;
        errDiv.style.display = 'block';
      }
    }

    async function loadDashboard() {
      try {
        var res = await fetch('/admin/api/data?token=' + encodeURIComponent(adminToken), {
          headers: { 'X-Admin-Token': adminToken, 'X-Admin-Secret': adminToken }
        });
        var data = await res.json();
        if (!data.ok) {
          localStorage.removeItem("wb_admin_token");
          adminToken = "";
          return false;
        }

        document.getElementById('logged-admin-user').innerText = data.admin_user || 'admin';
        document.getElementById('stat-total-licenses').innerText = (data.licenses || []).length;
        document.getElementById('stat-total-agents').innerText = (data.agents || []).length;
        
        var paidOrders = (data.orders || []).filter(function(o) { return o.status === 'PAID'; });
        document.getElementById('stat-total-orders').innerText = paidOrders.length;
        var totalRev = paidOrders.reduce(function(acc, cur) { return acc + parseFloat(cur.amount || 0); }, 0);
        document.getElementById('stat-total-revenue').innerText = '¥' + totalRev.toFixed(2);

        document.getElementById('tab-cnt-agents').innerText = (data.agents || []).length;
        document.getElementById('tab-cnt-licenses').innerText = (data.licenses || []).length;
        document.getElementById('tab-cnt-orders').innerText = (data.orders || []).length;

        renderAgentsTable(data.agents || []);
        renderLicensesTable(data.licenses || []);
        renderOrdersTable(data.orders || []);

        showDashboard();
        return true;
      } catch (e) {
        return false;
      }
    }

    function renderAgentsTable(agents) {
      var tbody = document.getElementById('agent-table-body');
      if (!agents || !agents.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:#64748b;">暂无代理商，点击右上角「➕ 创建新代理商」添加</td></tr>';
        return;
      }
      tbody.innerHTML = agents.map(function(ag) {
        var tier = (Number(ag.total_stores_issued || 0) < 100) ? 240.00 : 180.00;
        var username = ag.username || ag.agent_id;
        var password = ag.password || "(未设置)";
        var isFrozen = ag.status === 'FROZEN';
        var isSpecial = Number(ag.total_stores_issued || 0) >= 100;
        
        return '<tr>' +
          '<td><strong>' + ag.name + '</strong><br><small style="color:#64748b;">ID: ' + ag.agent_id + '</small></td>' +
          '<td><code>' + username + '</code> <span class="copy-link" data-copy="' + username + '" onclick="copyText(this.dataset.copy)">📋</span></td>' +
          '<td><code style="background:#f1f5f9;padding:2px 6px;border-radius:4px;">' + password + '</code> <span class="copy-link" data-copy="' + password + '" onclick="copyText(this.dataset.copy)">📋</span></td>' +
          '<td style="color:#059669;font-weight:700;font-size:15px;">¥' + Number(ag.balance || 0).toFixed(2) + '</td>' +
          '<td><strong>' + (ag.total_stores_issued || 0) + '</strong> 家</td>' +
          '<td><span class="badge ' + (isSpecial ? 'badge-active' : 'badge-paid') + '">¥' + tier.toFixed(2) + ' / 店 ' + (isSpecial ? '(特惠档)' : '(标准档)') + '</span></td>' +
          '<td><span class="badge ' + (isFrozen ? 'badge-banned' : 'badge-active') + '">' + (isFrozen ? '已冻结' : '正常合作') + '</span></td>' +
          '<td>' +
            '<button class="action-btn btn-renew" data-id="' + ag.agent_id + '" data-name="' + encodeURIComponent(ag.name) + '" onclick="rechargeAgent(this.dataset.id, decodeURIComponent(this.dataset.name))">💳 充值</button> ' +
            '<button class="action-btn btn-pwd" data-id="' + ag.agent_id + '" data-name="' + encodeURIComponent(ag.name) + '" onclick="resetAgentPwd(this.dataset.id, decodeURIComponent(this.dataset.name))">🔑 改密</button> ' +
            '<button class="action-btn ' + (isFrozen ? 'btn-unban' : 'btn-ban') + '" data-id="' + ag.agent_id + '" data-status="' + (isFrozen ? 'ACTIVE' : 'FROZEN') + '" onclick="toggleAgentStatus(this.dataset.id, this.dataset.status)">' + (isFrozen ? '解冻' : '冻结') + '</button>' +
          '</td>' +
          '</tr>';
      }).join('');
    }

    function renderLicensesTable(licenses) {
      var tbody = document.getElementById('license-table-body');
      if (!licenses || !licenses.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:#64748b;">暂无店铺授权数据</td></tr>';
        return;
      }
      tbody.innerHTML = licenses.map(function(lic) {
        var isBanned = lic.status === "BANNED";
        var srcTag = (lic.source && lic.source.startsWith('AGENT:'))
          ? '<span style="color:#6366f1; font-weight:600;">🤝 代理商 (' + (lic.agent_name || lic.source) + ')</span>'
          : lic.source === 'ALIPAY_SELF_SERVICE' ? '<span style="color:#1677ff; font-weight:600;">支付宝直购</span>'
          : lic.source === 'FREE_TRIAL_2DAYS' ? '<span style="color:#10b981; font-weight:600;">🎁 免费试用</span>' : '管理员签发';

        return '<tr>' +
          '<td><strong>' + (lic.name || "未命名客户") + '</strong><br><small style="color:#6366f1;">🏪 ' + (lic.store_name || lic.store || "默认店铺") + '</small></td>' +
          '<td><code>' + (lic.machine_id || "未激活首机") + '</code></td>' +
          '<td class="key-cell">' + lic.key + '</td>' +
          '<td>' + (lic.expires_at || "永久") + '</td>' +
          '<td>' + (lic.usage_count || 0) + ' 件</td>' +
          '<td>' + srcTag + '</td>' +
          '<td><span class="badge ' + (isBanned ? "badge-banned" : "badge-active") + '">' + (isBanned ? "已封禁" : "正常授权") + '</span></td>' +
          '<td>' +
            (isBanned
              ? '<button class="action-btn btn-unban" data-act="unban" data-key="' + encodeURIComponent(lic.key) + '" onclick="action(this.dataset.act, decodeURIComponent(this.dataset.key))">解封</button> '
              : '<button class="action-btn btn-ban" data-act="ban" data-key="' + encodeURIComponent(lic.key) + '" onclick="action(this.dataset.act, decodeURIComponent(this.dataset.key))">在线封禁</button> ') +
            '<button class="action-btn btn-renew" data-key="' + encodeURIComponent(lic.key) + '" onclick="renew(decodeURIComponent(this.dataset.key))">续期+365天</button>' +
          '</td>' +
          '</tr>';
      }).join('');
    }

    function renderOrdersTable(orders) {
      var tbody = document.getElementById('order-table-body');
      if (!orders || !orders.length) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:20px;color:#64748b;">暂无直营订单流水</td></tr>';
        return;
      }
      tbody.innerHTML = orders.map(function(ord) {
        var isPaid = ord.status === "PAID";
        return '<tr>' +
          '<td><code>' + ord.order_id + '</code></td>' +
          '<td><strong>' + (ord.plan_name || "-") + '</strong></td>' +
          '<td><strong style="color: #6366f1;">' + (ord.store_name || "-") + '</strong></td>' +
          '<td style="color: #059669; font-weight: 700;">¥' + (ord.amount || "0.00") + '</td>' +
          '<td>' + (ord.customer_name || "-") + '</td>' +
          '<td><code>' + (ord.machine_id || "-") + '</code></td>' +
          '<td><small>' + (ord.trade_no || "-") + '</small></td>' +
          '<td>' + (ord.paid_at || ord.created_at || "-") + '</td>' +
          '<td><span class="badge ' + (isPaid ? "badge-paid" : "badge-pending") + '">' + (isPaid ? "已支付" : "待支付") + '</span></td>' +
          '</tr>';
      }).join('');
    }

    async function openCreateAgentModal() {
      var name = prompt("请输入代理商名称 (例如：华东总代理-李总):");
      if (!name) return;
      var username = prompt("请输入代理商登录用户名 (留空自动生成):", "");
      var password = prompt("请输入代理商初始登录密码 (留空自动生成):", "");
      var balance = prompt("请输入初始充值预存金额 (元，例如 2400):", "2400");
      if (balance === null) return;

      var res = await fetch("/admin/api/agent/create?token=" + encodeURIComponent(adminToken), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
        body: JSON.stringify({
          name: name,
          username: username ? username.trim() : undefined,
          password: password ? password.trim() : undefined,
          initial_balance: parseFloat(balance) || 0
        })
      });
      var data = await res.json();
      if (data.ok) {
        alert("🎉 代理商创建成功！\\n" +
              "代理商名称：" + data.agent.name + "\\n" +
              "登录用户名：" + data.agent.username + "\\n" +
              "登录密码：" + data.agent.password + "\\n" +
              "预存余额：¥" + data.agent.balance + "\\n\\n" +
              "代理商登录入口：\\n" + location.origin + "/agent");
        loadDashboard();
      } else {
        alert("创建失败: " + data.error);
      }
    }

    async function resetAgentPwd(agentId, agentName) {
      var newPwd = prompt("请输入为代理商【" + agentName + "】设置的新密码 (至少 6 位):");
      if (!newPwd) return;
      var newUsername = prompt("如需同时修改或补全登录用户名，请输入 (留空保持不变):", "");
      var res = await fetch("/admin/api/agent/reset-password?token=" + encodeURIComponent(adminToken), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
        body: JSON.stringify({ agent_id: agentId, new_username: newUsername ? newUsername.trim() : undefined, new_password: newPwd })
      });
      var data = await res.json();
      if (data.ok) {
        alert("✅ 凭据更新成功！最新用户名: " + data.username + "，密码: " + data.new_password);
        loadDashboard();
      } else {
        alert("重置失败: " + data.error);
      }
    }

    async function rechargeAgent(agentId, agentName) {
      var amount = prompt("请输入为代理商【" + agentName + "】充值的金额 (元):", "2400");
      if (!amount) return;
      var res = await fetch("/admin/api/agent/recharge?token=" + encodeURIComponent(adminToken), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
        body: JSON.stringify({ agent_id: agentId, amount: parseFloat(amount) })
      });
      var data = await res.json();
      if (data.ok) {
        alert("✅ 充值成功！当前最新余额: ¥" + data.new_balance);
        loadDashboard();
      } else {
        alert("充值失败: " + data.error);
      }
    }

    async function toggleAgentStatus(agentId, newStatus) {
      if (!confirm("确认将该代理商状态更改为 " + newStatus + "？")) return;
      var res = await fetch("/admin/api/agent/status?token=" + encodeURIComponent(adminToken), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
        body: JSON.stringify({ agent_id: agentId, status: newStatus })
      });
      if (res.ok) { loadDashboard(); } else { alert("操作失败: " + await res.text()); }
    }

    async function action(type, key) {
      if (!confirm("确认对该授权执行 " + type + " 操作？")) return;
      var res = await fetch("/admin/api/" + type + "?token=" + encodeURIComponent(adminToken), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
        body: JSON.stringify({ license_key: decodeURIComponent(key) })
      });
      if (res.ok) { loadDashboard(); } else { alert("操作失败: " + await res.text()); }
    }

    async function renew(key) {
      var days = prompt("请输入要延期的天数 (默认 365 天):", "365");
      if (!days) return;
      var res = await fetch("/admin/api/renew?token=" + encodeURIComponent(adminToken), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
        body: JSON.stringify({ license_key: decodeURIComponent(key), days: parseInt(days) })
      });
      if (res.ok) { loadDashboard(); } else { alert("续期失败: " + await res.text()); }
    }

    function openChangeAdminPwdModal() {
      document.getElementById('admin-pwd-modal').style.display = 'flex';
    }
    function closeChangeAdminPwdModal() {
      document.getElementById('admin-pwd-modal').style.display = 'none';
    }

    async function doChangeAdminPwd() {
      var oldPwd = document.getElementById('adm-old-pwd').value;
      var newUser = document.getElementById('adm-new-user').value.trim();
      var newPwd = document.getElementById('adm-new-pwd').value;

      if (!oldPwd || !newPwd) {
        alert("请输入原密码与新密码！");
        return;
      }
      try {
        var res = await fetch('/admin/api/change-password?token=' + encodeURIComponent(adminToken), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Admin-Token': adminToken },
          body: JSON.stringify({ old_password: oldPwd, new_username: newUser, new_password: newPwd })
        });
        var data = await res.json();
        if (data.ok) {
          alert("✅ 超级管理员密码修改成功！请使用新密码重新登录。");
          closeChangeAdminPwdModal();
          doAdminLogout();
        } else {
          alert("修改失败: " + data.error);
        }
      } catch (e) {
        alert("请求异常: " + e.message);
      }
    }

    function doAdminLogout() {
      localStorage.removeItem("wb_admin_token");
      adminToken = "";
      showLogin();
    }

    init();
  </script>
</body>
</html>`;

      return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
    }

    // 6.5 Admin API: Create Agent: POST /admin/api/agent/create
    if (path === "/admin/api/agent/create" && method === "POST") {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      try {
        const { name, username, password, initial_balance = 0 } = await request.json();
        if (!name) return new Response(JSON.stringify({ ok: false, error: "缺少代理商名称" }), { status: 400, headers: corsHeaders });

        const agentId = `AGT_${Math.random().toString(36).substring(2, 7).toUpperCase()}`;
        const token = `AGT-SEC-${crypto.randomUUID().replace(/-/g, '').substring(0, 16)}`;
        const finalUsername = (username && username.trim()) ? username.trim() : `agent_${agentId.substring(4).toLowerCase()}`;
        const finalPassword = (password && password.trim()) ? password.trim() : Math.random().toString(36).substring(2, 10);

        // Check if username already exists
        const existing = await findAgentByUsername(finalUsername);
        if (existing) {
          return new Response(JSON.stringify({ ok: false, error: "该用户名已被其他代理商占用，请更换" }), { status: 400, headers: corsHeaders });
        }

        const agentRecord = {
          agent_id: agentId,
          name: name.trim(),
          username: finalUsername,
          password: finalPassword,
          token: token,
          balance: Number(initial_balance) || 0,
          total_stores_issued: 0,
          status: "ACTIVE",
          created_at: new Date().toISOString()
        };

        if (env.WB_LICENSES) {
          await env.WB_LICENSES.put(`AGENT:${agentId}`, JSON.stringify(agentRecord));
          await env.WB_LICENSES.put(`AGENT_USER:${finalUsername.toLowerCase()}`, agentId);
          await env.WB_LICENSES.put(`AGENT_TOKEN:${token}`, agentId);
        }

        return new Response(JSON.stringify({ ok: true, agent: agentRecord }), {
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 6.6 Admin API: Reset Agent Password: POST /admin/api/agent/reset-password
    if (path === "/admin/api/agent/reset-password" && method === "POST") {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      try {
        const { agent_id, new_username, new_password } = await request.json();
        if (!agent_id || !new_password) {
          return new Response(JSON.stringify({ ok: false, error: "缺少 agent_id 或新密码" }), { status: 400, headers: corsHeaders });
        }

        const raw = await env.WB_LICENSES.get(`AGENT:${agent_id}`);
        if (!raw) return new Response(JSON.stringify({ ok: false, error: "未找到该代理商" }), { status: 404, headers: corsHeaders });

        const agent = JSON.parse(raw);
        if (new_username && new_username.trim()) {
          const oldUser = agent.username;
          if (oldUser && oldUser.toLowerCase() !== new_username.trim().toLowerCase()) {
            await env.WB_LICENSES.delete(`AGENT_USER:${oldUser.toLowerCase()}`);
          }
          agent.username = new_username.trim();
          await env.WB_LICENSES.put(`AGENT_USER:${agent.username.toLowerCase()}`, agent.agent_id);
        } else if (!agent.username) {
          agent.username = `agent_${agent.agent_id.substring(4).toLowerCase()}`;
          await env.WB_LICENSES.put(`AGENT_USER:${agent.username.toLowerCase()}`, agent.agent_id);
        }
        agent.password = new_password.trim();
        agent.password_updated_at = new Date().toISOString();
        await env.WB_LICENSES.put(`AGENT:${agent_id}`, JSON.stringify(agent));

        return new Response(JSON.stringify({ ok: true, agent_id, username: agent.username, new_password: agent.password }), {
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 6.7 Admin API: Recharge Agent: POST /admin/api/agent/recharge
    if (path === "/admin/api/agent/recharge" && method === "POST") {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      try {
        const { agent_id, amount } = await request.json();
        if (!agent_id || amount === undefined) {
          return new Response(JSON.stringify({ ok: false, error: "缺少 agent_id 或充值金额" }), { status: 400, headers: corsHeaders });
        }

        const raw = await env.WB_LICENSES.get(`AGENT:${agent_id}`);
        if (!raw) return new Response(JSON.stringify({ ok: false, error: "未找到该代理商" }), { status: 404, headers: corsHeaders });

        const agent = JSON.parse(raw);
        agent.balance = Number((Number(agent.balance || 0) + Number(amount)).toFixed(2));
        agent.last_recharged_at = new Date().toISOString();
        await env.WB_LICENSES.put(`AGENT:${agent_id}`, JSON.stringify(agent));

        return new Response(JSON.stringify({ ok: true, agent_id, new_balance: agent.balance }), {
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 6.8 Admin API: Change Agent Status: POST /admin/api/agent/status
    if (path === "/admin/api/agent/status" && method === "POST") {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      try {
        const { agent_id, status } = await request.json();
        const raw = await env.WB_LICENSES.get(`AGENT:${agent_id}`);
        if (!raw) return new Response(JSON.stringify({ ok: false, error: "未找到代理商" }), { status: 404, headers: corsHeaders });

        const agent = JSON.parse(raw);
        agent.status = status;
        await env.WB_LICENSES.put(`AGENT:${agent_id}`, JSON.stringify(agent));

        return new Response(JSON.stringify({ ok: true, agent_id, status }), {
          headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // 6.9 Admin API: Remote Ban: POST /admin/api/ban
    if (path === "/admin/api/ban" && method === "POST") {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key, reason = "Manual ban by admin" } = await request.json();
      const kvKey = getLicenseKvKey(license_key);
      let val = await env.WB_LICENSES.get(kvKey);
      if (!val && license_key.length <= 512) val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      rec.status = "BANNED";
      rec.ban_reason = reason;
      rec.banned_at = new Date().toISOString();
      await env.WB_LICENSES.put(kvKey, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, status: "BANNED" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 6.10 Admin API: Remote Unban: POST /admin/api/unban
    if (path === "/admin/api/unban" && method === "POST") {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key } = await request.json();
      const kvKey = getLicenseKvKey(license_key);
      let val = await env.WB_LICENSES.get(kvKey);
      if (!val && license_key.length <= 512) val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      rec.status = "ACTIVE";
      delete rec.banned_at;
      delete rec.ban_reason;
      await env.WB_LICENSES.put(kvKey, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, status: "ACTIVE" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 6.11 Admin API: Remote Renewal: POST /admin/api/renew
    if (path === "/admin/api/renew" && method === "POST") {
      const auth = await verifyAdminAuth(request, env, url);
      if (!auth.isAuth) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key, days = 365 } = await request.json();
      const kvKey = getLicenseKvKey(license_key);
      let val = await env.WB_LICENSES.get(kvKey);
      if (!val && license_key.length <= 512) val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      let curExp = rec.expires_at ? new Date(rec.expires_at.replace(" ", "T")) : new Date();
      if (isNaN(curExp.getTime()) || curExp < new Date()) {
        curExp = new Date();
      }
      curExp.setDate(curExp.getDate() + Number(days));
      const pad = (n) => String(n).padStart(2, "0");
      rec.expires_at = `${curExp.getFullYear()}-${pad(curExp.getMonth() + 1)}-${pad(curExp.getDate())} 23:59:59`;
      await env.WB_LICENSES.put(kvKey, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, expires_at: rec.expires_at }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }
    return new Response("Not Found", { status: 404, headers: corsHeaders });
  }
};
