import crypto from 'node:crypto';
import { Buffer } from 'node:buffer';

/**
 * Cloudflare Workers Commercial License & Anti-Piracy Gateway + Alipay Self-Service Cashier
 * Pricing: ¥600 RMB per store (单店商业授权 ¥600.00 / 店铺)
 * Zero-server, zero-maintenance global edge authentication, remote management, and automated Alipay license dispensing.
 */

// Embedded default credentials
const DEFAULT_ALIPAY_APP_ID = "2021007100687379";
const DEFAULT_ALIPAY_PRIVATE_KEY_B64 = `MIIEugIAMA0GCSqGSIb3DQEBAQUABIIEpTCCBKECAAKCAQEAjSPTqDh+BumFzULXlAZKtnaxuG1+tIXX/JLtga4nzenBwcujEYAO7X525XgpNpsbB0lqsHmn8IzlbrEScFzewolpKF+xpcMXvrIW+Wf4f2W/mTkTuIBh1Dk0x7EP/Hw6VkX2E9qTtLjg9hxhf6eO9yCvNiYcVcsmQmgqbqG6dSmvKytVSnviVClMcV+yuk+e6dgZIsHf+KI2VWXZXgro2j6/uzI+uqlCSg+6zEnj+fgkYqXeyDxcugR+gn6Fl1hjvciIGVRkbFQf9C+vUndKkd96Sung7dBCiuly0ab9hV/mEiem2RB8VOouq5yvyS4XLecusOFfUisL3zN1OG3gLwIDAQABAoIBAGsF0rZJeA8HvqUB3XRqPPcVE/g0VxLONxRX2W8vPxGeAoVQQ+u+PhOKhN/F+QJmJN2mpxcAeP8n58XC0aeQVH4RMkMiJRP71qKMam1ekIkR/3JRXInYF9aUNliCBAxBqv7GeC1f3gb49eTJaokg5oCwMQwPZAcOT4mlcR+I1VmHTPfgycxWjT1tcDr0p7Xhnw1gA9A04soXyt3qflNRItMVMIc7dlhQnh3gBYsXF7Ze6CW2plqKkV7kb56XwLuxqGLEPlF8RKnmnzShfW8MEjxO7G9xDDAg/dduVy3Ay4lgq3JKtNdY0uQYZoVNh8e3KhT3wFYpyQwMaGalQFl+w0kCgYEAwFvDVfC3nlkVj3PpulzRmfsmLrkCYc+BNWQ+5W3JlkoMnNzd+K7Pdm3Kf6l/+jaCluCcZvhUaf4/+yjSdtcSkkpk5HsA/YjBFLd2FOUWIOLw33iedpAJpe78qhMl9J56fCai6IKw3pyCQi06nUhlx/djMs7j9oGJt8WOxek0RK0CgYEAu9X/BK0z1QTrAKbpjz4TwYvxHMRg6aZ/Ac8Wzpy854lBvetDtCN1vj9x5ujXnJ5ZrP2B4dfIcUk/ULOKuzvfvLV74EsXWdrgl8bsf7wnCwKCB4+csQBxABn8B3uc6axReI4t2T41u9n3SjcOZGI4JyznY63jQ87Yb6ZTSDMrd8sCgYB3y+5QJHVGgbaCu66xaMMEwbva10/beG7AwKjHG+Oy3HUUcB0xljUQTXoSnY5dVvtnWYUuP7PauwQ/uAGzD2i6gOhqvwwz2apd64/3nWB1pMBcfHM75aKMm9TxWrGFsfkYPruwUEw0p4YcDqz1bTQuICzAZMbmK3CIadnr+bualQKBgAkKKXW+KCpuTCkB32enYygDZh0uTkOwYZhisQRMgsLZ1jIfqmh29Gmtf/vO5OGCtWof4SpPSjQ5hDSMD3cnUIMycL3An2URpZFoX2VeVrqu6jcW8EGMdeO9XGW3yztrsZgNr6Mu3UMnIEGQGL84At/Px2sCqVdQExZ8eLGW1Na1AoGAYPJpodlLgcGD5srCgqiDm6WgmEJdj4UdxDNhixyatN3h+YOG1lJlLth2WHYwwP/A+5H7w1UgpmHQNt2U6PEB8Te6RG0Dhs1vOrPoqWfjcZUlC5HS0GaMGQUVE1qZyzIHWnmx2L3E1U7naJJsvwwvZ8zEqfOOG_SgQXBt2gCawVo=`;

const DEFAULT_ALIPAY_PUBLIC_KEY_B64 = `MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwdOBuGCeyxVO+NCZuEiIVk+har+YaYrW7GzWS3AEPinZ5sb/2oqymr3Coa8JmcmW5sah59Fro3d8SJCkFroRniPOZn/HohxP+8hz9Zh0L5vIWUYPz+fDF675wxzg5TappT0gOgADio+8LtrbPaB5T7i0VgN2qfytDJkFgLvweMHJaLz/WoXNVhVAcOqwj611TX3KlckFebOQQbwoSW4juaPf4qYBRMPSGZxzMo3sNtwKUmd0YHk0wtsbIRacCvfCC0lIo9cjZ2XPLQj4tGRob/X9XUK6EjHpCUpPrRMm+jBlz5B9XoND6SEJy2xpVVnij1fe8ux6ZTkfTygH/Er1UwIDAQAB`;

const DEFAULT_RSA_SIGNING_KEY_B64 = `MIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQC68iqR8hjHueryql/SsW895wtWV0QzXZzu6l0Db7kXAcI/dTrfRWjHock5gXoNj4KraCElPSNW0/EISgrxA6MZe3QyaEXv+i0hk+gaoKkSIZwj9KmIRtIqBuxlckro9tGNyCbS4snwlu+XLI6pkCyi1KU+4OZDS9YlscdVCzcUtSwGR7tnsoN+MNwtuvlYakIpA/rS2yxi90Btb5DYMlFcBf7d/UJqOPBa412B2hhxxd8eWR9QcoyjS2y32r1Eo5QW588fnm+s/XP0zNXWvRWcCsZPFwC/I0NlMRcYBibcyZApxdIMyu+7Kow+F0nZtMK5EKZUnxQ6tX8+xFTB/guPAgMBAAECggEAE/6KkbQe9QhBb1V24jCaq+LmJ4SLMCM3AaaMmYLS0k8cg2+lAvQy0gclCm16rFtI/SQp8ghT8JltEhc5NwXN5Tp69wPdVwlJgmnbTTMZt21jfG+nzNd7lYXKtXQ/5s1fJEGKmst+uv3+/2At8fIQPr9s3QjDbTcoiZI2C4vOMadFD9UlZKsXCOyCyW/TLwP5olaEfjYg4KyLqwnqtKEBJ2tsn/InS4qcvBytPzzu4O6tu4UUjPJtcTN+KlWv0vXXPacADBJAc/3oiaL0ekX325S1vlDP+D9RbV3gKh8hiZMl9xSvV5G1ABZlP2IjKYnmIETU4oLE4gh/qh64n5aZwQKBgQD3KBG3yAzHMMVaqiW2QOlQrm1dwjLz6oESdX/Rq252Y/yWzGHH5bZHgyuw6wWALn+AwChT0iPawmTfn4fLTGaaaYqvs5s9XZjUZxG6o/qJWyl8cGJkzDGyQiji6T1/sYwImL64MqmVfj5jMjMTl7yAitk0cdryBrVHglzG3xn2eQKBgQDBopLukadaeD29x0YbWUZ7sZxBolwwbjtjyzk3KysshVWRJLFGG0FYyGAEyFMIPxQpgAeYPSO0nn4SEYMHFJ3NSLkAJMhBCDWQCTI9PcYGYKiOkXnlASP0snhYgsNbhEg2A9sWe5I2FoXMmnMw0MJc+2o+DCvU5Eg6LCygyzQwRwKBgQDBgba1jEQs5EtwG80g75t8lsR75uMbw9vAhwxHLZBz0v7dVjGsX3aicNmRT8DjxgP/2vL4BYwa554w02dvTWb7uGxj+hwuJIzWp8fiuCYcyqolipwOzSyPo2r9lZ2Xz3uS83xHHStXJxtTcOc6jM+CWLOMcyP34DaoQTHAZsaeCQKBgQCjw55m3JLgZd852QZG7Qs6Y+1WaT10zFW4QdEDAqSCA8ZpedHgC/8JWnYytUXcLJUdwCUsMVE4We8f0uWxIFORodas827V6V57kfuGZe9Lx4XnBcxEzOEe+63ilb0pckgsPriVXC89RXElqN6RQ42OXCfvkBWl+OfJI0EfQJzD0wKBgQDFRc5Z538b448hjy/DeWMblOiB1LxZWsHEuvwRB8KXLpErKaBh47tggd/qVaOberh71g3WHkyUgGlSVatvZLamKEXBwu2dfRRKdux2pVXIGX6OueM6X4Q2UtUjsPH5B5C8E1ZmnhuARZFddlfpJbsgRHqKyb5VEIxys0nbyR9aLQ==`;

// Pricing Model: 600 RMB per store / 1 Year (按店铺收费，每店 600 元/年，支付当日起 365 天有效)
const PLANS = {
  single_store: {
    id: "single_store",
    name: "单店商业授权 (1 家店铺)",
    stores: 1,
    price: "600.00",
    original_price: "999.00",
    days: 365,
    desc: "1:1 店铺专属互斥锁定 · 1年有效(365天，自支付当日起算) · Ozon 极速搬家 · 50%大促折算 · 莫斯科1仓现货秒级注入 · 赠 1 次安全换店配额"
  },
  dual_store: {
    id: "dual_store",
    name: "双店进阶套餐 (2 家店铺)",
    stores: 2,
    price: "1200.00",
    original_price: "1998.00",
    days: 365,
    desc: "支持 2 家 Wildberries 店铺独立授权 · 1年有效(365天) · 专属一对一上架技术指导 · 双店矩阵卖家推荐"
  },
  triple_store: {
    id: "triple_store",
    name: "多店旗舰版 (3 家店铺)",
    stores: 3,
    price: "1800.00",
    original_price: "2997.00",
    days: 365,
    desc: "支持 3 家 Wildberries 店铺 · 3 个独立店铺授权码 · 1年有效(365天) · 团队规模化上架首选"
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
 * Node.js Crypto RSA-PSS SHA-256 license key generation (Default: 365 days / 1 year validity)
 */
function signLicenseKey(mid, customerName, storeName, days = 365, maxSessions = 1, privKeyB64 = DEFAULT_RSA_SIGNING_KEY_B64) {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const iatStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  
  const expDate = new Date(now.getTime() + (days > 0 ? days : 365) * 24 * 60 * 60 * 1000);
  const expStr = days > 0
    ? `${expDate.getFullYear()}-${pad(expDate.getMonth() + 1)}-${pad(expDate.getDate())} 23:59:59`
    : `${now.getFullYear() + 1}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} 23:59:59`;

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
    .filter(k => k !== 'sign' && k !== 'sign_type' && params[k] !== undefined && params[k] !== null && params[k] !== '')
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

    const adminSecret = env.ADMIN_SECRET || "WB-ADMIN-SECRET-2026";
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

      const recordJson = await env.WB_LICENSES.get(key);
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

      if (record.machine_id && mid && record.machine_id !== mid && record.machine_id !== "*") {
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
        await env.WB_LICENSES.put(key, JSON.stringify(record));
      }

      record.last_verified_at = new Date().toISOString();
      await env.WB_LICENSES.put(key, JSON.stringify(record));

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
        const recordJson = await env.WB_LICENSES.get(key);
        if (recordJson) {
          const record = JSON.parse(recordJson);
          record.usage_count = (record.usage_count || 0) + Number(amount);
          record.last_used_at = new Date().toISOString();
          await env.WB_LICENSES.put(key, JSON.stringify(record));
          return new Response(JSON.stringify({ ok: true, total_usage: record.usage_count }), {
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }
        return new Response(JSON.stringify({ ok: false, error: "License not found" }), { status: 404, headers: corsHeaders });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: e.message }), { status: 500, headers: corsHeaders });
      }
    }

    // ==========================================
    // 4. Alipay Cashier & Order APIs (¥600/Store)
    // ==========================================

    // 4.1 Cashier UI: GET /pay
    if (path === "/pay" && method === "GET") {
      const orderIdParam = url.searchParams.get("order_id") || "";
      const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Wildberries 极速上架助手 · 单店商业授权收银台</title>
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
      <h1>单店商业授权 · 支付宝收银台</h1>
      <p class="subtitle">单店 1:1 专属锁定 · 一机一码硬件绑定 · 支付 600 元/店秒级自动发码</p>
    </div>

    <div class="price-tag-banner">
      <div class="price-tag-info">
        <span class="price-tag-label">收费计费标准</span>
        <span class="price-tag-desc">按 Wildberries 店铺计费 (1店1码)</span>
      </div>
      <div class="price-tag-num">
        ¥600.00 <small>/ 店铺</small>
      </div>
    </div>

    <div id="checkout-section">
      <div class="form-group">
        <label>💻 目标电脑机器码 (Machine ID) <span style="color: #ef4444;">*</span></label>
        <input type="text" id="mid-input" class="input-box" placeholder="MID-XXXX-XXXX-XXXX-XXXX" />
        <div class="input-tip">
          💡 获取方法：在 Antigravity 对话框中输入「<code>获取机器码</code>」，复制专属硬件指纹粘贴在此。
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
        <div class="plan-card active" onclick="selectPlan('single_store')" id="plan-single_store">
          <div class="plan-badge">标准单店</div>
          <div class="plan-title">单店商业授权</div>
          <div class="plan-price">¥600<small>/1家店</small></div>
          <div class="plan-orig">原价 ¥999</div>
        </div>
        <div class="plan-card" onclick="selectPlan('dual_store')" id="plan-dual_store">
          <div class="plan-title">双店进阶版</div>
          <div class="plan-price">¥1200<small>/2家店</small></div>
          <div class="plan-orig">原价 ¥1998</div>
        </div>
        <div class="plan-card" onclick="selectPlan('triple_store')" id="plan-triple_store">
          <div class="plan-title">三店旗舰版</div>
          <div class="plan-price">¥1800<small>/3家店</small></div>
          <div class="plan-orig">原价 ¥2997</div>
        </div>
      </div>

      <button id="pay-btn" class="btn-pay" onclick="handlePay()">
        <svg style="width: 20px; height: 20px;" viewBox="0 0 1024 1024" fill="currentColor">
          <path d="M793.6 128H230.4C174.08 128 128 174.08 128 230.4v563.2C128 849.92 174.08 896 230.4 896h563.2c56.32 0 102.4-46.08 102.4-102.4V230.4C896 174.08 849.92 128 793.6 128z m-204.8 542.72c-20.48 5.12-40.96 10.24-66.56 15.36 51.2 56.32 128 97.28 215.04 117.76-25.6 20.48-56.32 35.84-92.16 46.08-76.8-25.6-143.36-71.68-189.44-133.12-51.2 15.36-107.52 25.6-163.84 25.6-112.64 0-168.96-51.2-168.96-128 0-71.68 56.32-128 153.6-128 66.56 0 128 15.36 179.2 40.96V409.6H332.8v-71.68h122.88V256h81.92v81.92h143.36v71.68H537.6v76.8c56.32 15.36 112.64 35.84 163.84 66.56l-46.08 69.12c-20.48-10.24-40.96-20.48-66.56-30.72z m-168.96-20.48c-40.96-15.36-87.04-25.6-133.12-25.6-56.32 0-87.04 25.6-87.04 61.44 0 40.96 35.84 61.44 92.16 61.44 35.84 0 76.8-5.12 128-20.48V650.24z"/>
        </svg>
        <span id="btn-text">支付宝一键安全支付 (¥600.00) · 立即发码</span>
      </button>

      <div class="features-list">
        <div class="feature-item">
          <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>
          支持 Ozon 标题、属性、多图、真实物理包装尺寸 100% 极速搬家至 WB
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
      <h2 style="color: #34d399; font-size: 18px; margin-bottom: 8px;">🎉 支付成功！专属店铺授权码已生成</h2>
      <p style="font-size: 13px; color: #a7f3d0;">您的专属商业授权已签发并自动完成云端登记：</p>
      
      <div id="license-key-box" class="lic-display"></div>
      
      <button class="btn-copy" onclick="copyLicense()">📋 一键复制授权码</button>
      
      <div style="margin-top: 16px; font-size: 12px; color: #cbd5e1; text-align: left; background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; line-height: 1.6;">
        <strong style="color: #38bdf8;">🚀 激活上架步骤：</strong><br>
        1. 点击上方绿色按钮复制授权码；<br>
        2. 回到 Antigravity 聊天窗口中输入：<br>
        <code style="color: #34d399; font-weight: bold; background: #0f172a; padding: 2px 6px; border-radius: 4px;">激活授权 &lt;复制的授权码&gt;</code><br>
        3. 绑定您的 Wildberries 店铺：<br>
        <code style="color: #38bdf8; font-weight: bold; background: #0f172a; padding: 2px 6px; border-radius: 4px;">切换店铺 店铺简称：我的WB店 API令牌：... 仓库ID：...</code><br>
        4. 输入 Ozon SKU 即可启动全自动极速搬家上架！
      </div>
    </div>
  </div>

  <script>
    let currentPlan = 'single_store';
    const planPrices = { single_store: '600.00', dual_store: '1200.00', triple_store: '1800.00' };

    function selectPlan(planId) {
      currentPlan = planId;
      document.querySelectorAll('.plan-card').forEach(el => el.classList.remove('active'));
      document.getElementById('plan-' + planId).classList.add('active');
      document.getElementById('btn-text').innerText = '支付宝一键安全支付 (¥' + planPrices[planId] + ') · 立即发码';
    }

    async function handlePay() {
      const mid = document.getElementById('mid-input').value.trim();
      const storeName = document.getElementById('store-input').value.trim();
      const customer = document.getElementById('customer-input').value.trim();

      if (!mid) {
        alert('请输入电脑机器码 (MID)！');
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
      payBtn.innerText = '正在生成支付宝收银台...';

      try {
        const res = await fetch('/api/pay/create-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mid: mid,
            store_name: storeName,
            name: customer || storeName || '商业客户',
            plan_id: currentPlan
          })
        });
        const data = await res.json();
        if (!data.ok) {
          alert('创建支付订单失败: ' + (data.error || '未知错误'));
          payBtn.disabled = false;
          selectPlan(currentPlan);
          return;
        }

        // Redirect to Alipay
        if (data.pay_url) {
          window.location.href = data.pay_url;
        } else {
          alert('未获取到支付跳转链接');
          payBtn.disabled = false;
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
          // Poll again
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
        const { mid, store_name = "我的WB店铺", name = "商业客户", plan_id = "single_store" } = body;

        if (!mid) {
          return new Response(JSON.stringify({ ok: false, error: "缺少机器码 (MID)" }), {
            status: 400,
            headers: { ...corsHeaders, "Content-Type": "application/json" }
          });
        }

        const plan = PLANS[plan_id] || PLANS.single_store;
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
          plan_id: plan.id
        };

        const bizContent = {
          out_trade_no: orderId,
          total_amount: plan.price,
          subject: `Wildberries极速上架助手-单店商业授权(¥600/店)`,
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

          const mid = extra.mid || (orderInfo && orderInfo.machine_id) || "MID-UNKNOWN";
          const customerName = extra.name || (orderInfo && orderInfo.customer_name) || "支付宝客户";
          const storeName = extra.store || (orderInfo && orderInfo.store_name) || "Wildberries店铺";
          const days = Number(extra.days || (orderInfo && orderInfo.days) || 365);

          // Sign the RSA license
          const { license_key, payload } = signLicenseKey(mid, customerName, storeName, days, 1, rsaSignKeyB64);

          // Save license to KV
          if (env.WB_LICENSES) {
            const licRecord = {
              name: customerName,
              store_name: storeName,
              machine_id: mid,
              max_sessions: 1,
              expires_at: payload.exp,
              type: "RSA-PSS-SHA256",
              created_at: new Date().toISOString(),
              source: "ALIPAY_SELF_SERVICE",
              trade_no: tradeNo,
              order_id: outTradeNo,
              amount: totalAmount,
              activated_sessions: []
            };
            await env.WB_LICENSES.put(license_key, JSON.stringify(licRecord));

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
    // 5. Admin Dashboard & Operations
    // ==========================================
    const reqSecret = request.headers.get("X-Admin-Secret") || url.searchParams.get("key");
    const isAdmin = reqSecret === adminSecret;

    // 5.1 Admin Web Dashboard: GET /admin
    if (path === "/admin" && method === "GET") {
      if (!isAdmin) {
        return new Response("Unauthorized: Invalid Admin Secret. Append ?key=YOUR_SECRET to the URL.", {
          status: 401,
          headers: { "Content-Type": "text/html; charset=utf-8" }
        });
      }

      // Fetch all licenses & orders from KV
      const listRes = await env.WB_LICENSES.list();
      const licenses = [];
      const orders = [];

      for (const k of listRes.keys) {
        const val = await env.WB_LICENSES.get(k.name);
        try {
          const parsed = JSON.parse(val);
          if (k.name.startsWith("ORD:")) {
            orders.push(parsed);
          } else {
            licenses.push({ key: k.name, ...parsed });
          }
        } catch (e) {
          licenses.push({ key: k.name, raw: val });
        }
      }

      // Sort orders descending
      orders.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));

      const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>商业授权与支付宝财务控制台 (¥600/店铺)</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #1e293b; padding: 24px; margin: 0; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 16px; margin-bottom: 24px; }
    h1 { font-size: 20px; font-weight: 700; color: #0f172a; margin: 0; }
    .stats-bar { display: flex; gap: 16px; margin-bottom: 24px; }
    .stat-card { background: #fff; padding: 16px 20px; border-radius: 8px; border: 1px solid #e2e8f0; flex: 1; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .stat-num { font-size: 24px; font-weight: 700; color: #0f172a; margin-top: 4px; }
    .stat-label { font-size: 12px; color: #64748b; font-weight: 600; }
    
    .nav-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
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
    .key-cell { font-family: monospace; font-size: 11px; word-break: break-all; max-width: 260px; }
  </style>
</head>
<body>
  <div class="header">
    <h1>🛡️ Wildberries 商业授权与支付宝财务控制台 (收费: ¥600/店)</h1>
    <a href="/pay" target="_blank" style="padding: 8px 16px; background: #1677ff; color: #fff; text-decoration: none; border-radius: 6px; font-size: 13px; font-weight: 600;">🛒 打开自选收银台</a>
  </div>

  <div class="stats-bar">
    <div class="stat-card">
      <div class="stat-label">总授权店铺数</div>
      <div class="stat-num">${licenses.length}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">在线正常店铺</div>
      <div class="stat-num" style="color: #10b981;">${licenses.filter(l => l.status !== 'BANNED').length}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">支付宝成交订单</div>
      <div class="stat-num" style="color: #3b82f6;">${orders.filter(o => o.status === 'PAID').length}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">累计交易金额</div>
      <div class="stat-num" style="color: #8b5cf6;">¥${orders.filter(o => o.status === 'PAID').reduce((acc, cur) => acc + parseFloat(cur.amount || 0), 0).toFixed(2)}</div>
    </div>
  </div>

  <div class="nav-tabs">
    <button class="tab-btn active" onclick="switchTab('licenses')">🔑 店铺授权列表 (${licenses.length})</button>
    <button class="tab-btn" onclick="switchTab('orders')">💳 支付宝财务订单 (${orders.length})</button>
  </div>

  <div id="tab-licenses">
    <table>
      <thead>
        <tr>
          <th>客户 / 店铺名称</th>
          <th>绑定机器码 (MID)</th>
          <th>授权码 (License Key)</th>
          <th>授权有效期</th>
          <th>累积用量</th>
          <th>来源</th>
          <th>状态</th>
          <th>管理操作</th>
        </tr>
      </thead>
      <tbody>
        ${licenses.map(lic => `
          <tr>
            <td>
              <strong>${lic.name || "未命名客户"}</strong><br>
              <small style="color: #6366f1;">🏪 ${lic.store_name || lic.store || "默认店铺"}</small>
            </td>
            <td><code>${lic.machine_id || "未激活首机"}</code></td>
            <td class="key-cell">${lic.key}</td>
            <td>${lic.expires_at || "永久"}</td>
            <td>${lic.usage_count || 0} 件</td>
            <td>${lic.source === 'ALIPAY_SELF_SERVICE' ? '<span style="color:#1677ff; font-weight:600;">支付宝购 (¥600/店)</span>' : '管理员签发'}</td>
            <td>
              <span class="badge ${lic.status === "BANNED" ? "badge-banned" : "badge-active"}">
                ${lic.status === "BANNED" ? "已封禁" : "正常授权"}
              </span>
            </td>
            <td>
              ${lic.status === "BANNED" 
                ? `<button class="action-btn btn-unban" onclick="action('unban', '${encodeURIComponent(lic.key)}')">解封</button>`
                : `<button class="action-btn btn-ban" onclick="action('ban', '${encodeURIComponent(lic.key)}')">在线封禁</button>`
              }
              <button class="action-btn btn-renew" onclick="renew('${encodeURIComponent(lic.key)}')">续期+365天</button>
            </td>
          </tr>
        `).join("")}
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
      <tbody>
        ${orders.map(ord => `
          <tr>
            <td><code>${ord.order_id}</code></td>
            <td><strong>${ord.plan_name || "-"}</strong></td>
            <td><strong style="color: #6366f1;">${ord.store_name || "-"}</strong></td>
            <td style="color: #059669; font-weight: 700;">¥${ord.amount || "0.00"}</td>
            <td>${ord.customer_name || "-"}</td>
            <td><code>${ord.machine_id || "-"}</code></td>
            <td><small>${ord.trade_no || "-"}</small></td>
            <td>${ord.paid_at || ord.created_at || "-"}</td>
            <td>
              <span class="badge ${ord.status === "PAID" ? "badge-paid" : "badge-pending"}">
                ${ord.status === "PAID" ? "已支付" : "待支付"}
              </span>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  </div>

  <script>
    const adminKey = "${reqSecret}";
    function switchTab(tab) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      if (tab === 'licenses') {
        document.getElementById('tab-licenses').style.display = 'block';
        document.getElementById('tab-orders').style.display = 'none';
        event.target.classList.add('active');
      } else {
        document.getElementById('tab-licenses').style.display = 'none';
        document.getElementById('tab-orders').style.display = 'block';
        event.target.classList.add('active');
      }
    }

    async function action(type, key) {
      if (!confirm("确认对该授权执行 " + type + " 操作？")) return;
      const res = await fetch("/admin/api/" + type + "?key=" + adminKey, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ license_key: decodeURIComponent(key) })
      });
      if (res.ok) { location.reload(); } else { alert("操作失败: " + await res.text()); }
    }
    async function renew(key) {
      const days = prompt("请输入要延期的天数 (默认 365 天):", "365");
      if (!days) return;
      const res = await fetch("/admin/api/renew?key=" + adminKey, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ license_key: decodeURIComponent(key), days: parseInt(days) })
      });
      if (res.ok) { location.reload(); } else { alert("续期失败: " + await res.text()); }
    }
  </script>
</body>
</html>`;

      return new Response(html, {
        headers: { "Content-Type": "text/html; charset=utf-8" }
      });
    }

    // 5.2 Admin API: Remote Ban / Revoke: POST /admin/api/ban
    if (path === "/admin/api/ban" && method === "POST") {
      if (!isAdmin) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key, reason = "Manual ban by admin" } = await request.json();
      const val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      rec.status = "BANNED";
      rec.ban_reason = reason;
      rec.banned_at = new Date().toISOString();
      await env.WB_LICENSES.put(license_key, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, status: "BANNED" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 5.3 Admin API: Remote Unban: POST /admin/api/unban
    if (path === "/admin/api/unban" && method === "POST") {
      if (!isAdmin) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key } = await request.json();
      const val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      rec.status = "ACTIVE";
      delete rec.banned_at;
      delete rec.ban_reason;
      await env.WB_LICENSES.put(license_key, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, status: "ACTIVE" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    // 5.4 Admin API: Remote Renewal: POST /admin/api/renew
    if (path === "/admin/api/renew" && method === "POST") {
      if (!isAdmin) return new Response("Unauthorized", { status: 401, headers: corsHeaders });
      const { license_key, days = 365 } = await request.json();
      const val = await env.WB_LICENSES.get(license_key);
      if (!val) return new Response("Not found", { status: 404, headers: corsHeaders });
      const rec = JSON.parse(val);
      let curExp = rec.expires_at ? new Date(rec.expires_at.replace(" ", "T")) : new Date();
      if (isNaN(curExp.getTime()) || curExp < new Date()) {
        curExp = new Date();
      }
      curExp.setDate(curExp.getDate() + Number(days));
      const pad = (n) => String(n).padStart(2, "0");
      rec.expires_at = `${curExp.getFullYear()}-${pad(curExp.getMonth() + 1)}-${pad(curExp.getDate())} 23:59:59`;
      await env.WB_LICENSES.put(license_key, JSON.stringify(rec));
      return new Response(JSON.stringify({ ok: true, license_key, expires_at: rec.expires_at }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" }
      });
    }

    return new Response("Not Found", { status: 404, headers: corsHeaders });
  }
};
