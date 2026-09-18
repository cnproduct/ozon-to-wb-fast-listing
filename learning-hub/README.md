# WB Skill 集中经验接收服务

独立 Cloudflare Worker + D1。客户本机仅上传经筛选的五个经验字段；原始对话、身份、商品编号、凭据和日志不得上传。服务端再次校验内容、去重，并在仅管理员可访问的 `/admin` 页面展示候选和审核状态。

## 路由

- `GET /health`：仅返回健康状态。
- `POST /api/ingest`：使用单机上传令牌的 Bearer 认证，请求体为 `{ "items": [{"category":"故障","observation":"...","outcome":"...","suggestion":"...","evidence":"代码验证"}] }`。每批最多 20 条。
- `GET /admin`：浏览器 HTTP Basic 认证，用户名 `admin`，密码为部署时设置的 `ADMIN_TOKEN` Secret。
- `GET /api/admin/summary`：管理员统计 API。
- `POST /api/admin/tokens`：管理员生成一次性显示的上传令牌；每台用户设备单独签发。
- `POST /api/admin/tokens/revoke`：管理员撤销指定令牌。

令牌只在 Cloudflare Secrets 和各设备本机私有配置中保存；D1 中只存上传令牌哈希和去标识化经验。D1 与正式授权网关完全分离。

## 部署与接入

用 Wrangler 在 `learning-hub/` 目录创建 D1 并将 ID 填入 `wrangler.jsonc`，运行 `wrangler d1 migrations apply DB --remote`，部署 Worker，然后以 `wrangler secret put ADMIN_TOKEN` 写入管理员密钥。部署后通过管理员 API 为每台设备生成上传令牌，把接收地址和该令牌存入该设备 `~/.codex/wb-skill-learning/hub-config.json`（权限 0600）。`python scripts/publish_learning.py` 只读取 `candidates.jsonl` 中经过本地筛选的五个字段并批量上传；服务器按内容去重，重复执行安全。

管理员在仪表盘中“采纳”只表示进入人工修订队列，不会自动修改 Skill、合并 PR 或部署。所有上传方须知晓本地候选将发送至集中服务。
