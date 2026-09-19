# WB Skill 集中经验接收服务

独立 Cloudflare Worker + D1。客户本机仅上传经筛选的五个经验字段；原始对话、身份、商品编号、凭据和日志不得上传。服务端再次校验内容、去重，并在仅管理员可访问的 `/admin` 页面展示候选和审核状态。

## 路由

- `GET /health`：仅返回健康状态。
- `POST /api/ingest`：使用单机上传令牌的 Bearer 认证，请求体为 `{ "items": [{"category":"故障","observation":"...","outcome":"...","suggestion":"...","evidence":"代码验证"}] }`。每批最多 20 条。
- `GET /api/rules/latest`：使用同一台设备的 Bearer 令牌，返回最新累计规则版本和以该设备令牌生成的 HMAC-SHA256 签名。
- `GET /admin`：未登录的浏览器跳转至管理员密码表单；密码为部署时设置的 `ADMIN_TOKEN` Secret。登录成功后使用 12 小时、`HttpOnly`、`Secure`、`SameSite=Strict` 的签名会话 Cookie。管理员 API 仍支持 HTTP Basic 认证，用户名为 `admin`。
- `GET /api/admin/summary`：管理员统计 API，包含审核状态、类别及最近七天每日新增。
- `POST /api/admin/tokens`：管理员生成一次性显示的上传令牌；每台用户设备单独签发。
- `POST /api/admin/tokens/revoke`：管理员撤销指定令牌。
- `POST /api/admin/lessons/delete`：管理员按内容指纹永久删除误收的候选。
- `POST /admin/publish`：管理员将已采纳、尚未发布的结论组成新的累计规则版本。

令牌只在 Cloudflare Secrets 和各设备本机私有配置中保存；D1 中只存上传令牌哈希和去标识化经验。D1 与正式授权网关完全分离。

## 部署与接入

用 Wrangler 在 `learning-hub/` 目录创建 D1 并将 ID 填入 `wrangler.jsonc`，运行 `wrangler d1 migrations apply DB --remote`，部署 Worker，然后以 `wrangler secret put ADMIN_TOKEN` 写入管理员密钥。部署后通过管理员 API 为每台设备生成上传令牌，把接收地址和该令牌存入该设备 `~/.codex/wb-skill-learning/hub-config.json`（权限 0600）。`python scripts/publish_learning.py` 只读取 `candidates.jsonl` 中经过本地筛选的五个字段并批量上传；服务器按内容去重，重复执行安全。

管理员在仪表盘中“采纳”只表示进入待发布队列。“发布”会生成供已配置客户端拉取的签名规则版本，但不会自动执行真实业务操作、合并代码或修改正在运行的旧对话。客户端用 `scripts/sync_learning_rules.py` 验证签名和版本后，只更新 `~/.gemini/GEMINI.md` 中的 WB 受管区块，并保留其他全局规则。所有上传方须知晓本地候选将发送至集中服务。

在设备配置好专属令牌后运行 `python scripts/install_learning_rule_sync.py`。安装器同时启用两个全局 Sidecar：每 15 分钟同步签名规则；每天本机时间 06:00 由 `scripts/update_skill_from_git.py` 更新 `~/.gemini/config/skills/ozon-to-wb-fast-listing`。完整 Skill 只接受官方仓库 `main` 的 GitHub 已验证提交和安全快进；发现本地修改、来源变化、历史改写、Skill 身份不符或更新后编译失败时停止更新并写入本机状态，不覆盖现有安装。既有仓库允许使用 CRLF 换行，避免将正常换行误判为内容错误。
