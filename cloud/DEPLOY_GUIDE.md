# Cloudflare Workers 云端鉴权网关部署指南

> **前置条件**：使用可管理该 Worker、KV 与 Durable Objects 的 Cloudflare 账号。免费试用的单 IP 三窗口配额需要 SQLite Durable Object 绑定。

---

## 部署方式：使用 Wrangler CLI

本版本由 `entry.js`、`worker.js`、`trial_ip_limiter.js` 和 Wrangler 的 Durable Object 迁移配置组成。网页编辑器只粘贴 `worker.js` 无法创建配额对象，会让试用签发停止。先核对线上独有的支付和授权逻辑，配置新的 Secret 并完成旧码迁移，再由 Wrangler 部署；不要直接覆盖生产 Worker。

### 既有 Worker 发布步骤

1. 备份当前 Worker 部署版本和 `WB_LICENSES` 授权记录，核对真实店铺 ID、到期时间和支付配置。
2. 在 Cloudflare Secret 中安全设置 `RSA_SIGNING_KEY`、`ADMIN_SECRET`；使用支付宝时设置 `ALIPAY_PRIVATE_KEY` 和核对 `ALIPAY_PUBLIC_KEY`、`ALIPAY_APP_ID`。不要把私钥写进源码或普通变量。
3. 在 `cloud/` 执行 `wrangler deploy --dry-run`，确认出现 `TRIAL_IP_LIMITER` Durable Object 和 `WB_LICENSES` KV 绑定；隔离环境先验证 3 窗口及并发限制。
4. 执行 `wrangler deploy`；验证首领、重复领、第 4 窗口拒绝、旧正式授权、支付回调和真实用户路径。

## Wrangler 命令

在 `cloud/` 目录执行。已有生产 KV 的 ID 已写入 `wrangler.toml`；新账号须先建立自己的 KV 并替换该 ID。

```bash
npm install -g wrangler
wrangler login
wrangler deploy --dry-run
# 完成旧码迁移、Secret 设置和隔离环境验证后：
wrangler deploy
```

---

## 访问与管理说明

部署完成后，Cloudflare 会为您生成一个全球唯一的免费域名，例如：
`https://wb-auth-gateway.<your-username>.workers.dev`

### 1. 访问可视化 Web 商业看板
在任何电脑或手机浏览器打开：
`https://wb-auth-gateway.<your-username>.workers.dev/admin`
- 即可实时查看全网客户激活状态、机器码、累计搬家上架件数；
- 随时点击 **【封禁】**、**【解封】**、**【+30天】**、**【+1年】** 实行远程控制！

### 2. 客户端配置
在客户端的 `config.json` 或环境变量中配置您的云端网关地址：
```json
{
  "cloud_auth_url": "https://wb-auth-gateway.<your-username>.workers.dev"
}
```
新版客户端在授权和上架前核验云端状态；授权到期、封禁或网关不可达时停止上架并显示原因。旧安装包需升级后才会采用该逻辑。
