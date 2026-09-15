/**
 * ==============================================================================
 * Wildberries 极速搬家助手 - Cloudflare Workers 商业授权网关与可视化用量看板
 * (Cloudflare Serverless License Gateway & Admin Dashboard)
 * ==============================================================================
 * 特性：
 * 1. 零服务器成本：运行于 Cloudflare 免费版 Workers (每日 100,000 次免费请求)；
 * 2. 全球边缘毫秒级响应：实时验真、在线秒级封禁、充值续费与用量统计；
 * 3. 自带精美 HTML5 可视化 Web 管理后台 (/admin)：无需额外部署前端，开箱即用；
 * 4. 高可靠持久化：依托 Cloudflare KV (WB_LICENSES) 分布式存储。
 * ==============================================================================
 */

const DEFAULT_ADMIN_SECRET = "WB-ADMIN-SECRET-2026";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const adminSecret = env.ADMIN_SECRET || DEFAULT_ADMIN_SECRET;

    // CORS 跨域处理
    if (request.method === "OPTIONS") {
      return handleCors();
    }

    try {
      // 1. 客户端验真接口: POST /api/verify
      if (path === "/api/verify" && request.method === "POST") {
        return await handleVerify(request, env);
      }

      // 2. 客户端上架用量上报: POST /api/usage/record
      if (path === "/api/usage/record" && request.method === "POST") {
        return await handleRecordUsage(request, env);
      }

      // 3. 管理员: 在线封禁 POST /api/admin/ban
      if (path === "/api/admin/ban" && request.method === "POST") {
        if (!checkAdminAuth(request, adminSecret)) return unauthResponse();
        return await handleAdminBan(request, env);
      }

      // 4. 管理员: 解除封禁 POST /api/admin/unban
      if (path === "/api/admin/unban" && request.method === "POST") {
        if (!checkAdminAuth(request, adminSecret)) return unauthResponse();
        return await handleAdminUnban(request, env);
      }

      // 5. 管理员: 充值续期 POST /api/admin/renew
      if (path === "/api/admin/renew" && request.method === "POST") {
        if (!checkAdminAuth(request, adminSecret)) return unauthResponse();
        return await handleAdminRenew(request, env);
      }

      // 6. 管理员: 获取全部授权列表 GET /api/admin/list
      if (path === "/api/admin/list" && request.method === "GET") {
        if (!checkAdminAuth(request, adminSecret)) return unauthResponse();
        return await handleAdminList(env);
      }

      // 7. 可视化 Web 管理面板: GET /admin
      if (path === "/admin") {
        return handleAdminDashboard(url, adminSecret, env);
      }

      // 8. 默认健康检查根路由
      if (path === "/" || path === "/health") {
        return jsonResponse({
          status: "ONLINE",
          service: "Wildberries Fast Listing Cloud Auth Gateway",
          version: "v3.0.0",
          server_time: new Date().toISOString()
        });
      }

      return jsonResponse({ error: "Endpoint Not Found" }, 404);
    } catch (err) {
      return jsonResponse({ error: err.message, stack: err.stack }, 500);
    }
  }
};

/**
 * 客户端授权验真处理器
 */
async function handleVerify(request, env) {
  const body = await request.json();
  const { license_key, machine_id, conversation_id } = body;

  if (!license_key) {
    return jsonResponse({ valid: false, reason: "EMPTY_LICENSE", message: "授权码不能为空" }, 400);
  }

  const clientIp = request.headers.get("cf-connecting-ip") || "unknown";
  const kvKey = `lic:${license_key}`;
  let record = await getKv(env, kvKey);

  // 首次云端登记 (自动将合规 RSA 凭证录入云端数据库)
  if (!record) {
    record = {
      license_key,
      machine_id: machine_id || "*",
      customer_name: body.customer_name || "自主激活客户",
      status: "ACTIVE",
      ban_reason: "",
      expires_at: body.expires_at || "2027-12-31 23:59:59",
      max_sessions: body.max_sessions || 1,
      total_uploaded: 0,
      created_at: new Date().toISOString(),
      last_seen: new Date().toISOString(),
      client_ip: clientIp
    };
    await putKv(env, kvKey, record);
  } else {
    // 更新最后活跃时间与 IP
    record.last_seen = new Date().toISOString();
    record.client_ip = clientIp;
  }

  // 1. 检查是否已被管理员在线封禁
  if (record.status === "BANNED") {
    return jsonResponse({
      valid: false,
      status: "BANNED",
      reason: "BANNED",
      message: `🚨【该商业授权已被管理员在线封禁】原因：${record.ban_reason || "违规使用或退款注销"}`
    });
  }

  // 2. 检查硬件机器码是否匹配
  if (record.machine_id && record.machine_id !== "*" && machine_id) {
    if (record.machine_id.toUpperCase() !== machine_id.toUpperCase()) {
      return jsonResponse({
        valid: false,
        status: "MACHINE_MISMATCH",
        reason: "MACHINE_MISMATCH",
        message: `🛑【硬件机器码不匹配】授权绑定机器码 [${record.machine_id}]，当前运行机器码 [${machine_id}]，严禁跨设备运行！`
      });
    }
  }

  // 3. 检查有效期
  if (record.expires_at && record.expires_at !== "unlimited") {
    const expDt = new Date(record.expires_at.replace(" ", "T"));
    if (new Date() > expDt) {
      record.status = "EXPIRED";
      await putKv(env, kvKey, record);
      return jsonResponse({
        valid: false,
        status: "EXPIRED",
        reason: "EXPIRED",
        message: `⏰【商业授权已到期】该授权已于 ${record.expires_at} 到期，请联系管理员续费充值！`
      });
    }
  }

  // 保存最新记录并返回成功
  await putKv(env, kvKey, record);

  return jsonResponse({
    valid: true,
    status: "ACTIVE",
    customer_name: record.customer_name,
    expires_at: record.expires_at,
    total_uploaded: record.total_uploaded || 0,
    server_time: new Date().toISOString()
  });
}

/**
 * 客户端上报搬家上架件数
 */
async function handleRecordUsage(request, env) {
  const body = await request.json();
  const { license_key, items_count } = body;
  const count = parseInt(items_count || 0);

  if (!license_key || count <= 0) {
    return jsonResponse({ success: false, message: "参数无效" }, 400);
  }

  const kvKey = `lic:${license_key}`;
  let record = await getKv(env, kvKey);
  if (!record) {
    record = {
      license_key,
      total_uploaded: 0,
      created_at: new Date().toISOString()
    };
  }

  record.total_uploaded = (record.total_uploaded || 0) + count;
  record.last_upload_at = new Date().toISOString();
  await putKv(env, kvKey, record);

  return jsonResponse({
    success: true,
    added: count,
    total_uploaded: record.total_uploaded
  });
}

/**
 * 管理员在线封禁
 */
async function handleAdminBan(request, env) {
  const { license_key, reason } = await request.json();
  if (!license_key) return jsonResponse({ success: false, message: "缺少 license_key" }, 400);

  const kvKey = `lic:${license_key}`;
  let record = await getKv(env, kvKey);
  if (!record) {
    record = { license_key, created_at: new Date().toISOString() };
  }

  record.status = "BANNED";
  record.ban_reason = reason || "违反服务条款或恶意倒卖";
  record.banned_at = new Date().toISOString();
  await putKv(env, kvKey, record);

  return jsonResponse({
    success: true,
    message: `✅ 已成功封禁授权码 [${license_key}]`,
    record
  });
}

/**
 * 管理员解除封禁
 */
async function handleAdminUnban(request, env) {
  const { license_key } = await request.json();
  if (!license_key) return jsonResponse({ success: false, message: "缺少 license_key" }, 400);

  const kvKey = `lic:${license_key}`;
  let record = await getKv(env, kvKey);
  if (!record) return jsonResponse({ success: false, message: "记录不存在" }, 404);

  record.status = "ACTIVE";
  record.ban_reason = "";
  record.unbanned_at = new Date().toISOString();
  await putKv(env, kvKey, record);

  return jsonResponse({
    success: true,
    message: `✅ 已成功解封授权码 [${license_key}]`,
    record
  });
}

/**
 * 管理员充值续期
 */
async function handleAdminRenew(request, env) {
  const { license_key, add_days } = await request.json();
  const days = parseInt(add_days || 30);
  if (!license_key) return jsonResponse({ success: false, message: "缺少 license_key" }, 400);

  const kvKey = `lic:${license_key}`;
  let record = await getKv(env, kvKey);
  if (!record) return jsonResponse({ success: false, message: "记录不存在" }, 404);

  let baseDt = new Date();
  if (record.expires_at && record.expires_at !== "unlimited") {
    const curExp = new Date(record.expires_at.replace(" ", "T"));
    if (curExp > baseDt) {
      baseDt = curExp;
    }
  }

  baseDt.setDate(baseDt.getDate() + days);
  const newExpStr = `${baseDt.toISOString().slice(0, 10)} 23:59:59`;

  record.expires_at = newExpStr;
  if (record.status === "EXPIRED") {
    record.status = "ACTIVE";
  }
  record.renewed_at = new Date().toISOString();
  await putKv(env, kvKey, record);

  return jsonResponse({
    success: true,
    message: `✅ 已成功为 [${record.customer_name || license_key}] 续费 ${days} 天！`,
    new_expires_at: newExpStr,
    record
  });
}

/**
 * 管理员获取全部列表
 */
async function handleAdminList(env) {
  const list = [];
  if (env.WB_LICENSES) {
    const keys = await env.WB_LICENSES.list({ prefix: "lic:" });
    for (const k of keys.keys) {
      const data = await env.WB_LICENSES.get(k.name, "json");
      if (data) list.push(data);
    }
  }
  return jsonResponse({ total: list.length, items: list });
}

/**
 * 可视化 Web 管理看板
 */
async function handleAdminDashboard(url, adminSecret, env) {
  const keyParam = url.searchParams.get("key");
  const isAuthed = keyParam === adminSecret;

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WB 极速上架助手 - 商业授权与用量看板</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --border: #334155;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .container { max-width: 1280px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
    .title { font-size: 22px; font-weight: bold; display: flex; align-items: center; gap: 8px; }
    .badge-pro { background: linear-gradient(135deg, #6366f1, #a855f7); color: #fff; padding: 4px 10px; border-radius: 9999px; font-size: 12px; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .stat-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
    .stat-title { font-size: 13px; color: var(--text-muted); margin-bottom: 8px; }
    .stat-value { font-size: 28px; font-weight: bold; }
    .stat-green { color: var(--success); }
    .stat-red { color: var(--danger); }
    .stat-indigo { color: var(--primary); }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
    .card-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }
    th { background: #182234; padding: 14px 16px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
    td { padding: 14px 16px; border-bottom: 1px solid var(--border); }
    tr:hover { background: rgba(255,255,255,0.02); }
    .status-badge { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    .status-ACTIVE { background: rgba(16,185,129,0.15); color: var(--success); border: 1px solid var(--success); }
    .status-BANNED { background: rgba(239,68,68,0.15); color: var(--danger); border: 1px solid var(--danger); }
    .status-EXPIRED { background: rgba(245,158,11,0.15); color: var(--warning); border: 1px solid var(--warning); }
    .btn { padding: 6px 12px; border-radius: 6px; border: none; font-size: 12px; font-weight: 600; cursor: pointer; transition: 0.2s; }
    .btn-ban { background: var(--danger); color: white; margin-right: 6px; }
    .btn-unban { background: var(--success); color: white; margin-right: 6px; }
    .btn-renew { background: var(--primary); color: white; }
    .btn:hover { opacity: 0.85; }
    .login-box { max-width: 400px; margin: 100px auto; background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 32px; text-align: center; }
    .input { width: 100%; padding: 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: white; margin: 16px 0; }
  </style>
</head>
<body>
  <div class="container">
    ${!isAuthed ? `
      <div class="login-box">
        <h2>🔒 管理员安全登录</h2>
        <p style="color: var(--text-muted); margin-top: 8px; font-size: 14px;">请输入 ADMIN_SECRET 口令以访问商业控制中心</p>
        <form method="GET" action="/admin">
          <input type="password" name="key" class="input" placeholder="输入管理密钥" required autofocus>
          <button type="submit" class="btn btn-renew" style="width: 100%; padding: 10px;">解锁登录</button>
        </form>
      </div>
    ` : `
      <div class="header">
        <div class="title">
          <span>🚀 WB 极速搬家助手 · 云端商业授权与用量看板</span>
          <span class="badge-pro">PRO 商业版</span>
        </div>
        <div>
          <span style="color: var(--text-muted); font-size: 13px; margin-right: 12px;">全球边缘节点: Cloudflare</span>
          <a href="/admin" class="btn btn-renew">刷新数据</a>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-title">活跃商户授权</div>
          <div class="stat-value stat-green" id="stat-active">-</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">已封禁恶意商户</div>
          <div class="stat-value stat-red" id="stat-banned">-</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">累计上架商品总数</div>
          <div class="stat-value stat-indigo" id="stat-uploads">-</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>商户授权档案列表 (实时在线控制)</h3>
          <span id="stat-total" style="color: var(--text-muted); font-size: 13px;"></span>
        </div>
        <table>
          <thead>
            <tr>
              <th>商户名称</th>
              <th>绑定机器码 (Machine ID)</th>
              <th>状态</th>
              <th>累计上架件数</th>
              <th>有效期至</th>
              <th>最后活跃时间</th>
              <th>在线控制操作</th>
            </tr>
          </thead>
          <tbody id="table-body">
            <tr><td colspan="7" style="text-align: center; color: var(--text-muted);">正在加载实时数据...</td></tr>
          </tbody>
        </table>
      </div>

      <script>
        const ADMIN_KEY = "${keyParam}";
        async function loadData() {
          try {
            const res = await fetch("/api/admin/list", {
              headers: { "Authorization": "Bearer " + ADMIN_KEY }
            });
            const data = await res.json();
            const items = data.items || [];
            
            let activeCount = 0, bannedCount = 0, totalUploads = 0;
            const tbody = document.getElementById("table-body");
            tbody.innerHTML = "";

            if (items.length === 0) {
              tbody.innerHTML = "<tr><td colspan='7' style='text-align: center; color: var(--text-muted); padding: 30px;'>暂无已激活的商户记录</td></tr>";
            }

            items.forEach(it => {
              if (it.status === "ACTIVE") activeCount++;
              if (it.status === "BANNED") bannedCount++;
              totalUploads += (it.total_uploaded || 0);

              const tr = document.createElement("tr");
              tr.innerHTML = \`
                <td><strong>\${it.customer_name || "未知客户"}</strong></td>
                <td><code style="background: #0f172a; padding: 2px 6px; border-radius: 4px; font-size: 12px;">\${it.machine_id || "*"}</code></td>
                <td><span class="status-badge status-\${it.status}">\${it.status}</span></td>
                <td><strong style="color: #6366f1;">\${it.total_uploaded || 0} 件</strong></td>
                <td>\${it.expires_at || "永久"}</td>
                <td style="color: var(--text-muted); font-size: 12px;">\${it.last_seen ? it.last_seen.slice(0, 19).replace('T', ' ') : '-'}</td>
                <td>
                  \${it.status === "BANNED" ? 
                    \`<button class="btn btn-unban" onclick="unbanLic('\${it.license_key}')">解封</button>\` : 
                    \`<button class="btn btn-ban" onclick="banLic('\${it.license_key}')">封禁</button>\`
                  }
                  <button class="btn btn-renew" onclick="renewLic('\${it.license_key}', 30)">+30天</button>
                  <button class="btn btn-renew" onclick="renewLic('\${it.license_key}', 365)" style="background: #a855f7;">+1年</button>
                </td>
              \`;
              tbody.appendChild(tr);
            });

            document.getElementById("stat-active").innerText = activeCount;
            document.getElementById("stat-banned").innerText = bannedCount;
            document.getElementById("stat-uploads").innerText = totalUploads + " 件";
            document.getElementById("stat-total").innerText = "共 " + items.length + " 家商户档案";
          } catch (e) {
            alert("加载数据异常: " + e.message);
          }
        }

        async function banLic(key) {
          const reason = prompt("请输入封禁原因（例如：倒卖软件/退款）：", "违规盗版封禁");
          if (!reason) return;
          await fetch("/api/admin/ban", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Authorization": "Bearer " + ADMIN_KEY },
            body: JSON.stringify({ license_key: key, reason })
          });
          loadData();
        }

        async function unbanLic(key) {
          if (!confirm("确认解封该商户？")) return;
          await fetch("/api/admin/unban", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Authorization": "Bearer " + ADMIN_KEY },
            body: JSON.stringify({ license_key: key })
          });
          loadData();
        }

        async function renewLic(key, days) {
          if (!confirm("确认为该商户续费 " + days + " 天？")) return;
          await fetch("/api/admin/renew", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Authorization": "Bearer " + ADMIN_KEY },
            body: JSON.stringify({ license_key: key, add_days: days })
          });
          loadData();
        }

        loadData();
      </script>
    `}
  </div>
</body>
</html>`;

  return new Response(html, {
    headers: { "Content-Type": "text/html; charset=utf-8" }
  });
}

/**
 * 辅助工具函数
 */
function checkAdminAuth(request, adminSecret) {
  const authHeader = request.headers.get("Authorization") || "";
  const token = authHeader.replace(/^Bearer\s+/i, "").trim();
  return token === adminSecret;
}

function unauthResponse() {
  return jsonResponse({ error: "Unauthorized: Invalid Admin Secret" }, 401);
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }
  });
}

function handleCors() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }
  });
}

// 内存容错回退机制（兼容本地调试或无 KV 绑定的极速运行测试）
const IN_MEMORY_KV = new Map();

async function getKv(env, key) {
  if (env && env.WB_LICENSES) {
    return await env.WB_LICENSES.get(key, "json");
  }
  return IN_MEMORY_KV.get(key) || null;
}

async function putKv(env, key, value) {
  if (env && env.WB_LICENSES) {
    await env.WB_LICENSES.put(key, JSON.stringify(value));
  } else {
    IN_MEMORY_KV.set(key, value);
  }
}
