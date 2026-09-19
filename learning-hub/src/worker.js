const CATEGORIES = new Set(['故障', '平台变化', '政策变化', '商品', '物流', '用户操作', '其他']);
const EVIDENCE = new Set(['平台回执', '官方来源', '代码验证', '用户反馈', '待核实']);
const STATUS = new Set(['candidate', 'approved', 'published', 'rejected']);
const FIELDS = ['category', 'observation', 'outcome', 'suggestion', 'evidence'];
const SENSITIVE = /(?:api[_ -]?key|token|secret|private[_ -]?key|license[_ -]?key|authorization|bearer|password|conversation[_ -]?id|chat[_ -]?id|store[_ -]?id|shop[_ -]?id|sku|nmid|barcode|订单号|手机号|授权码|密钥|店铺名|客户名|(?:\d{1,3}\.){3}\d{1,3}|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{5,}\b|https?:\/\/\S+|\/Users\/\S+|[A-Za-z]:\\\S+)/i;
const LIMIT_BYTES = 16384;
const ADMIN_COOKIE = 'wb_learning_admin';
const ADMIN_SESSION_MS = 12 * 60 * 60 * 1000;

function sameSecret(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  const aa = new TextEncoder().encode(a);
  const bb = new TextEncoder().encode(b);
  let mismatch = aa.length ^ bb.length;
  for (let i = 0; i < Math.max(aa.length, bb.length); i++) mismatch |= (aa[i] || 0) ^ (bb[i] || 0);
  return mismatch === 0;
}

async function sha256(text) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('');
}

function randomToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function headers(type) {
  return {
    'Content-Type': type,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY'
  };
}

function json(value, status = 200, extra = {}) {
  return new Response(JSON.stringify(value), {status, headers: {...headers('application/json; charset=utf-8'), ...extra}});
}

function unauthorized() {
  return json({error: 'unauthorized'}, 401, {'WWW-Authenticate': 'Basic realm="WB Learning Hub"'});
}

function basicAdminAuthorized(request, env) {
  const authorization = request.headers.get('Authorization') || '';
  if (!authorization.startsWith('Basic ') || !env.ADMIN_TOKEN) return false;
  try {
    const decoded = atob(authorization.slice(6));
    const delimiter = decoded.indexOf(':');
    return delimiter >= 0 && sameSecret(decoded.slice(0, delimiter), 'admin') && sameSecret(decoded.slice(delimiter + 1), env.ADMIN_TOKEN);
  } catch { return false; }
}

async function hmacHex(secret, text) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']);
  const bytes = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('');
}

function cookieValue(request, name) {
  const cookies = request.headers.get('Cookie') || '';
  for (const part of cookies.split(';')) {
    const delimiter = part.indexOf('=');
    if (delimiter >= 0 && part.slice(0, delimiter).trim() === name) return part.slice(delimiter + 1).trim();
  }
  return '';
}

async function cookieAdminAuthorized(request, env) {
  if (!env.ADMIN_TOKEN) return false;
  const session = cookieValue(request, ADMIN_COOKIE);
  const match = /^(\d{13})\.([0-9a-f]{64})$/.exec(session);
  if (!match) return false;
  const expires = Number(match[1]);
  if (expires <= Date.now() || expires > Date.now() + ADMIN_SESSION_MS) return false;
  const expected = await hmacHex(env.ADMIN_TOKEN, `wb-learning-admin:${match[1]}`);
  return sameSecret(match[2], expected);
}

async function adminAuthorized(request, env) {
  return basicAdminAuthorized(request, env) || await cookieAdminAuthorized(request, env);
}

async function adminSessionCookie(env) {
  const expires = String(Date.now() + ADMIN_SESSION_MS);
  const signature = await hmacHex(env.ADMIN_TOKEN, `wb-learning-admin:${expires}`);
  return `${ADMIN_COOKIE}=${expires}.${signature}; Path=/admin; Max-Age=${ADMIN_SESSION_MS / 1000}; HttpOnly; Secure; SameSite=Strict`;
}

function loginPage(error = '') {
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WB Skill 管理员登录</title><style>body{font:15px system-ui,sans-serif;background:#f6f8fb;color:#192536;display:grid;min-height:90vh;place-items:center}.box{width:min(360px,calc(100% - 3rem));background:#fff;padding:1.5rem;border-radius:12px;box-shadow:0 2px 14px #0002}label,input,button{display:block;width:100%;box-sizing:border-box}input,button{padding:.75rem;margin-top:.5rem;border-radius:7px;border:1px solid #ccd3dd}button{margin-top:1rem;background:#2255aa;color:#fff;border:0}.error{color:#a61b1b}</style><main class="box"><h1>管理员登录</h1><p>WB Skill 内部经验仪表盘</p>${error ? '<p class="error">密码不正确，请重试。</p>' : ''}<form method="post" action="/admin/login"><label>管理员密码<input type="password" name="password" required autocomplete="current-password"></label><button type="submit">登录</button></form></main></html>`;
  return new Response(html, {status: error ? 401 : 200, headers: {...headers('text/html; charset=utf-8'), 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"}});
}

function sameOrigin(request) {
  const origin = request.headers.get('Origin');
  return origin === new URL(request.url).origin;
}

async function limitedText(request, max = LIMIT_BYTES) {
  const declared = Number(request.headers.get('Content-Length') || 0);
  if (declared > max) throw new Error('too_large');
  const reader = request.body?.getReader();
  if (!reader) throw new Error('empty_body');
  let size = 0;
  const chunks = [];
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    size += value.length;
    if (size > max) { await reader.cancel(); throw new Error('too_large'); }
    chunks.push(value);
  }
  const all = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { all.set(chunk, offset); offset += chunk.length; }
  return new TextDecoder('utf-8', {fatal: true}).decode(all);
}

function cleanField(value) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (text.length < 2 || text.length > 400 || /[\u0000-\u001f\u007f]/.test(text) || SENSITIVE.test(text)) return null;
  return text;
}

function validateLesson(value) {
  if (!value || Array.isArray(value) || typeof value !== 'object') return null;
  if (Object.keys(value).length !== FIELDS.length || Object.keys(value).some(key => !FIELDS.includes(key))) return null;
  const item = {};
  for (const key of FIELDS) {
    item[key] = cleanField(value[key]);
    if (!item[key]) return null;
  }
  if (!CATEGORIES.has(item.category) || !EVIDENCE.has(item.evidence)) return null;
  return item;
}

async function activeDeviceToken(request, env) {
  const bearer = request.headers.get('Authorization') || '';
  if (!/^Bearer [A-Za-z0-9_-]{40,100}$/.test(bearer)) return null;
  const token = bearer.slice(7);
  const active = await env.DB.prepare('SELECT id FROM ingest_tokens WHERE token_hash = ? AND revoked_at IS NULL').bind(await sha256(token)).first();
  return active ? token : null;
}

async function ingest(request, env) {
  if (request.headers.get('Content-Type')?.split(';')[0] !== 'application/json') return json({error: 'content_type'}, 415);
  if (!await activeDeviceToken(request, env)) return json({error: 'unauthorized'}, 401);
  let body;
  try { body = JSON.parse(await limitedText(request)); } catch { return json({error: 'invalid_json_or_size'}, 400); }
  if (!body || Object.keys(body).length !== 1 || !Array.isArray(body.items) || body.items.length < 1 || body.items.length > 20) return json({error: 'invalid_batch'}, 400);
  const items = body.items.map(validateLesson);
  if (items.some(item => !item)) return json({error: 'invalid_or_sensitive_item'}, 422);
  const now = new Date().toISOString();
  const statements = [];
  for (const item of items) {
    const fingerprint = await sha256(JSON.stringify(FIELDS.map(key => item[key])));
    statements.push(env.DB.prepare('INSERT OR IGNORE INTO lessons (fingerprint, category, observation, outcome, suggestion, evidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)').bind(fingerprint, item.category, item.observation, item.outcome, item.suggestion, item.evidence, now));
  }
  const results = await env.DB.batch(statements);
  const accepted = results.reduce((sum, result) => sum + (result.meta?.changes || 0), 0);
  return json({accepted, duplicate: items.length - accepted});
}

async function latestRules(request, env) {
  const token = await activeDeviceToken(request, env);
  if (!token) return json({error: 'unauthorized'}, 401);
  const release = await env.DB.prepare('SELECT version, rules_json, created_at FROM rule_releases ORDER BY version DESC LIMIT 1').first();
  if (!release) return new Response(null, {status: 204, headers: headers('application/json; charset=utf-8')});
  let rules;
  try { rules = JSON.parse(release.rules_json); } catch { return json({error: 'release_data'}, 500); }
  const payload = JSON.stringify({version: release.version, created_at: release.created_at, rules});
  return json({algorithm: 'HMAC-SHA256', payload, signature: await hmacHex(token, payload)});
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
}

async function dashboard(env, request) {
  const status = new URL(request.url).searchParams.get('status');
  if (status && !STATUS.has(status)) return json({error: 'invalid_status'}, 400);
  const totals = await env.DB.prepare('SELECT review_status, COUNT(*) AS count FROM lessons GROUP BY review_status').all();
  const categories = await env.DB.prepare('SELECT category, COUNT(*) AS count FROM lessons GROUP BY category ORDER BY count DESC').all();
  const daily = await env.DB.prepare('SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS count FROM lessons WHERE created_at >= ? GROUP BY substr(created_at, 1, 10) ORDER BY day DESC').bind(new Date(Date.now() - 7 * 86400000).toISOString()).all();
  const latestRelease = await env.DB.prepare('SELECT version, item_count, created_at FROM rule_releases ORDER BY version DESC LIMIT 1').first();
  const deviceTokens = (await env.DB.prepare('SELECT id, created_at, revoked_at FROM ingest_tokens ORDER BY created_at DESC LIMIT 50').all()).results || [];
  const query = status
    ? env.DB.prepare('SELECT fingerprint, category, observation, outcome, suggestion, evidence, review_status, created_at FROM lessons WHERE review_status = ? ORDER BY created_at DESC LIMIT 100').bind(status)
    : env.DB.prepare('SELECT fingerprint, category, observation, outcome, suggestion, evidence, review_status, created_at FROM lessons ORDER BY created_at DESC LIMIT 100');
  const lessons = (await query.all()).results || [];
  const totalMap = Object.fromEntries((totals.results || []).map(row => [row.review_status, row.count]));
  const cards = (categories.results || []).map(row => `<span class="pill">${escapeHtml(row.category)} ${row.count}</span>`).join(' ');
  const days = (daily.results || []).map(row => `<span class="pill">${escapeHtml(row.day)}：${row.count}</span>`).join(' ');
  const csrf = await hmacHex(env.ADMIN_TOKEN, 'wb-learning-admin-csrf');
  const rows = lessons.map(row => `<tr><td>${escapeHtml(row.created_at.slice(0, 10))}</td><td>${escapeHtml(row.category)}</td><td>${escapeHtml(row.observation)}</td><td>${escapeHtml(row.outcome)}</td><td>${escapeHtml(row.suggestion)}</td><td>${escapeHtml(row.evidence)}</td><td>${escapeHtml(row.review_status)}</td><td>${row.review_status === 'candidate' ? `<form method="post" action="/admin/review"><input type="hidden" name="csrf" value="${csrf}"><input type="hidden" name="fingerprint" value="${escapeHtml(row.fingerprint)}"><button name="status" value="approved">采纳</button><button name="status" value="rejected">排除</button></form>` : ''}</td></tr>`).join('');
  const publish = totalMap.approved ? `<form method="post" action="/admin/publish"><input type="hidden" name="csrf" value="${csrf}"><button type="submit">发布 ${totalMap.approved} 条已采纳规则</button></form>` : '';
  const releaseText = latestRelease ? `当前发布版本 ${latestRelease.version}，共 ${latestRelease.item_count} 条规则` : '尚未发布规则版本';
  const tokenRows = deviceTokens.map(row => `<tr><td><code>${escapeHtml(row.id)}</code></td><td>${escapeHtml(row.created_at.slice(0, 19))}</td><td>${row.revoked_at ? '已撤销' : '有效'}</td><td>${row.revoked_at ? '' : `<form method="post" action="/admin/token/revoke"><input type="hidden" name="csrf" value="${csrf}"><input type="hidden" name="id" value="${escapeHtml(row.id)}"><button type="submit">撤销</button></form>`}</td></tr>`).join('');
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>WB Skill 内部经验仪表盘</title><style>body{font:15px system-ui,sans-serif;margin:2rem;background:#f6f8fb;color:#192536}h1{margin-bottom:.3rem}.muted{color:#667085}.stats{display:flex;gap:1rem;flex-wrap:wrap;margin:1.5rem 0}.stat,.panel{background:white;padding:1rem;border-radius:10px;box-shadow:0 1px 4px #0001}.stat strong{display:block;font-size:1.7rem}.pill{display:inline-block;background:#e9f1ff;padding:.35rem .7rem;border-radius:20px;margin:.2rem}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #e5e9f0;padding:.7rem;min-width:90px}td:nth-child(3),td:nth-child(4),td:nth-child(5){min-width:220px}button{margin:.15rem;padding:.3rem .5rem}a{color:#2255aa}.logout{float:right}code{word-break:break-all}</style><form class="logout" method="post" action="/admin/logout"><input type="hidden" name="csrf" value="${csrf}"><button type="submit">退出</button></form><h1>WB Skill 内部经验仪表盘</h1><p class="muted">仅展示去标识化候选；采纳后由管理员单独发布为签名规则版本。</p><div class="stats"><div class="stat">待核验<strong>${totalMap.candidate || 0}</strong></div><div class="stat">待发布<strong>${totalMap.approved || 0}</strong></div><div class="stat">已发布<strong>${totalMap.published || 0}</strong></div><div class="stat">已排除<strong>${totalMap.rejected || 0}</strong></div></div><div class="panel"><strong>${releaseText}</strong>${publish}<p><strong>最近七天新增</strong></p><p>${days || '暂无记录'}</p><strong>类别</strong><p>${cards || '暂无记录'}</p><p><a href="/admin">全部</a> · <a href="/admin?status=candidate">待核验</a> · <a href="/admin?status=approved">待发布</a> · <a href="/admin?status=published">已发布</a> · <a href="/admin?status=rejected">已排除</a></p></div><h2>设备令牌</h2><div class="panel"><p>每台用户电脑单独生成一个。令牌只在生成后显示一次。</p><form method="post" action="/admin/token/new"><input type="hidden" name="csrf" value="${csrf}"><button type="submit">生成设备令牌</button></form></div><div class="scroll"><table><thead><tr><th>令牌 ID</th><th>创建时间</th><th>状态</th><th>操作</th></tr></thead><tbody>${tokenRows || '<tr><td colspan="4">暂无设备令牌</td></tr>'}</tbody></table></div><h2>最近记录</h2><div class="scroll"><table><thead><tr><th>日期</th><th>类别</th><th>观察</th><th>实际结果</th><th>建议</th><th>证据</th><th>状态</th><th>审核</th></tr></thead><tbody>${rows || '<tr><td colspan="8">暂无记录</td></tr>'}</tbody></table></div></html>`;
  return new Response(html, {headers: {...headers('text/html; charset=utf-8'), 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"}});
}

function deviceTokenPage(id, token) {
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>新设备令牌</title><style>body{font:15px system-ui,sans-serif;background:#f6f8fb;color:#192536;max-width:760px;margin:3rem auto;padding:0 1rem}.box{background:#fff;padding:1.5rem;border-radius:12px;box-shadow:0 2px 14px #0002}textarea{width:100%;box-sizing:border-box;padding:.8rem;min-height:90px;font:14px ui-monospace,monospace}code{word-break:break-all}a{color:#2255aa}</style><main class="box"><h1>新设备令牌</h1><p><strong>请立即复制。离开页面后无法再次查看。</strong></p><p>令牌 ID：<code>${escapeHtml(id)}</code></p><textarea readonly>${escapeHtml(token)}</textarea><p>在用户电脑运行 <code>configure_learning_client.py</code>，将此令牌粘贴到隐藏输入框。</p><p><a href="/admin">返回管理员仪表盘</a></p></main></html>`;
  return new Response(html, {headers: {...headers('text/html; charset=utf-8'), 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"}});
}

async function publishApproved(env) {
  const approved = (await env.DB.prepare("SELECT fingerprint, category, suggestion FROM lessons WHERE review_status = 'approved' AND published_version IS NULL ORDER BY reviewed_at, created_at").all()).results || [];
  if (!approved.length) return null;
  const latest = await env.DB.prepare('SELECT version, rules_json FROM rule_releases ORDER BY version DESC LIMIT 1').first();
  let existing = [];
  if (latest) {
    try { existing = JSON.parse(latest.rules_json); } catch { throw new Error('release_data'); }
  }
  const combined = [...existing, ...approved.map(row => ({category: row.category, rule: row.suggestion}))];
  const seen = new Set();
  const rules = combined.filter(item => {
    const key = JSON.stringify([item.category, item.rule]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (rules.length > 50) throw new Error('release_limit');
  const version = (latest?.version || 0) + 1;
  const now = new Date().toISOString();
  const statements = [env.DB.prepare('INSERT INTO rule_releases (version, rules_json, item_count, created_at) VALUES (?, ?, ?, ?)').bind(version, JSON.stringify(rules), rules.length, now)];
  for (const row of approved) statements.push(env.DB.prepare("UPDATE lessons SET review_status = 'published', published_version = ? WHERE fingerprint = ? AND review_status = 'approved' AND published_version IS NULL").bind(version, row.fingerprint));
  await env.DB.batch(statements);
  return version;
}

async function adminApi(request, env, pathname) {
  if (request.method === 'POST') {
    const origin = request.headers.get('Origin');
    if (origin && origin !== new URL(request.url).origin) return json({error: 'origin'}, 403);
    if (request.headers.get('Content-Type')?.split(';')[0] !== 'application/json') return json({error: 'content_type'}, 415);
  }
  if (pathname === '/api/admin/summary' && request.method === 'GET') {
    const statuses = await env.DB.prepare('SELECT review_status, COUNT(*) AS count FROM lessons GROUP BY review_status').all();
    const categories = await env.DB.prepare('SELECT category, COUNT(*) AS count FROM lessons GROUP BY category').all();
    const daily = await env.DB.prepare('SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS count FROM lessons WHERE created_at >= ? GROUP BY substr(created_at, 1, 10) ORDER BY day DESC').bind(new Date(Date.now() - 7 * 86400000).toISOString()).all();
    return json({statuses: statuses.results || [], categories: categories.results || [], daily: daily.results || []});
  }
  if (pathname === '/api/admin/tokens' && request.method === 'POST') {
    const token = randomToken();
    const id = crypto.randomUUID();
    await env.DB.prepare('INSERT INTO ingest_tokens (id, token_hash, created_at) VALUES (?, ?, ?)').bind(id, await sha256(token), new Date().toISOString()).run();
    return json({id, token}, 201);
  }
  if (pathname === '/api/admin/tokens/revoke' && request.method === 'POST') {
    let body;
    try { body = JSON.parse(await limitedText(request, 1024)); } catch { return json({error: 'invalid_json'}, 400); }
    if (typeof body?.id !== 'string' || !/^[0-9a-f-]{36}$/.test(body.id)) return json({error: 'invalid_id'}, 400);
    await env.DB.prepare('UPDATE ingest_tokens SET revoked_at = ? WHERE id = ?').bind(new Date().toISOString(), body.id).run();
    return json({ok: true});
  }
  if (pathname === '/api/admin/lessons/delete' && request.method === 'POST') {
    let body;
    try { body = JSON.parse(await limitedText(request, 1024)); } catch { return json({error: 'invalid_json'}, 400); }
    if (typeof body?.fingerprint !== 'string' || !/^[0-9a-f]{64}$/.test(body.fingerprint)) return json({error: 'invalid_fingerprint'}, 400);
    const result = await env.DB.prepare('DELETE FROM lessons WHERE fingerprint = ?').bind(body.fingerprint).run();
    return json({deleted: result.meta?.changes || 0});
  }
  return json({error: 'not_found'}, 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === '/health' && request.method === 'GET') return json({ok: true});
      if (url.pathname === '/api/ingest' && request.method === 'POST') return await ingest(request, env);
      if (url.pathname === '/api/rules/latest' && request.method === 'GET') return await latestRules(request, env);
      if (url.pathname === '/admin/login' && request.method === 'GET') return loginPage();
      if (url.pathname === '/admin/login' && request.method === 'POST') {
        let form;
        try { form = new URLSearchParams(await limitedText(request, 1024)); } catch { return loginPage('invalid'); }
        if (!sameSecret(form.get('password'), env.ADMIN_TOKEN)) return loginPage('invalid');
        return new Response(null, {status: 303, headers: {'Location': url.origin + '/admin', 'Set-Cookie': await adminSessionCookie(env), ...headers('text/plain; charset=utf-8')}});
      }
      if (url.pathname.startsWith('/admin') || url.pathname.startsWith('/api/admin/')) {
        if (!await adminAuthorized(request, env)) {
          if (url.pathname.startsWith('/api/')) return unauthorized();
          return Response.redirect(url.origin + '/admin/login', 303);
        }
        if (url.pathname === '/admin/logout' && request.method === 'POST') {
          let form;
          try { form = new URLSearchParams(await limitedText(request, 1024)); } catch { return json({error: 'invalid_form'}, 400); }
          if (!sameSecret(form.get('csrf'), await hmacHex(env.ADMIN_TOKEN, 'wb-learning-admin-csrf'))) return json({error: 'csrf'}, 403);
          return new Response(null, {status: 303, headers: {'Location': url.origin + '/admin/login', 'Set-Cookie': `${ADMIN_COOKIE}=; Path=/admin; Max-Age=0; HttpOnly; Secure; SameSite=Strict`, ...headers('text/plain; charset=utf-8')}});
        }
        if (url.pathname === '/admin' && request.method === 'GET') return await dashboard(env, request);
        if (url.pathname === '/admin/token/new' && request.method === 'POST') {
          let form;
          try { form = new URLSearchParams(await limitedText(request, 1024)); } catch { return json({error: 'invalid_form'}, 400); }
          if (!sameSecret(form.get('csrf'), await hmacHex(env.ADMIN_TOKEN, 'wb-learning-admin-csrf'))) return json({error: 'csrf'}, 403);
          const token = randomToken();
          const id = crypto.randomUUID();
          await env.DB.prepare('INSERT INTO ingest_tokens (id, token_hash, created_at) VALUES (?, ?, ?)').bind(id, await sha256(token), new Date().toISOString()).run();
          return deviceTokenPage(id, token);
        }
        if (url.pathname === '/admin/token/revoke' && request.method === 'POST') {
          let form;
          try { form = new URLSearchParams(await limitedText(request, 1024)); } catch { return json({error: 'invalid_form'}, 400); }
          if (!sameSecret(form.get('csrf'), await hmacHex(env.ADMIN_TOKEN, 'wb-learning-admin-csrf'))) return json({error: 'csrf'}, 403);
          const id = form.get('id');
          if (!/^[0-9a-f-]{36}$/.test(id || '')) return json({error: 'invalid_id'}, 400);
          await env.DB.prepare('UPDATE ingest_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL').bind(new Date().toISOString(), id).run();
          return Response.redirect(url.origin + '/admin', 303);
        }
        if (url.pathname === '/admin/publish' && request.method === 'POST') {
          let form;
          try { form = new URLSearchParams(await limitedText(request, 1024)); } catch { return json({error: 'invalid_form'}, 400); }
          if (!sameSecret(form.get('csrf'), await hmacHex(env.ADMIN_TOKEN, 'wb-learning-admin-csrf'))) return json({error: 'csrf'}, 403);
          await publishApproved(env);
          return Response.redirect(url.origin + '/admin', 303);
        }
        if (url.pathname === '/admin/review' && request.method === 'POST') {
          let form;
          try { form = new URLSearchParams(await limitedText(request, 1024)); } catch { return json({error: 'invalid_form'}, 400); }
          if (!sameSecret(form.get('csrf'), await hmacHex(env.ADMIN_TOKEN, 'wb-learning-admin-csrf'))) return json({error: 'csrf'}, 403);
          const fingerprint = form.get('fingerprint');
          const status = form.get('status');
          if (!/^[0-9a-f]{64}$/.test(fingerprint || '') || !['approved', 'rejected'].includes(status)) return json({error: 'invalid_review'}, 400);
          await env.DB.prepare('UPDATE lessons SET review_status = ?, reviewed_at = ? WHERE fingerprint = ? AND review_status = ?').bind(status, new Date().toISOString(), fingerprint, 'candidate').run();
          return Response.redirect(url.origin + '/admin', 303);
        }
        if (url.pathname.startsWith('/api/admin/')) return await adminApi(request, env, url.pathname);
      }
      return json({error: 'not_found'}, 404);
    } catch {
      return json({error: 'internal_error'}, 500);
    }
  }
};
