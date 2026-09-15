# Cloudflare Workers 云端鉴权网关与用量看板 2分钟部署指南 (永久免费)

> **前置条件**：注册一个 [Cloudflare 免费账号](https://dash.cloudflare.com/)（无需绑定信用卡，终身免费，每天可承受 100,000 次请求）。

---

## 极速部署方式一：网页端直接复制粘贴 (推荐，无需安装任何命令行工具)

### 步骤 1：创建 Worker 服务
1. 打开并登录 [Cloudflare 控制台](https://dash.cloudflare.com/)；
2. 在左侧菜单点击 **Compute (Workers & Pages)** ➔ 点击右上角 **Create application** (创建应用程序)；
3. 选择 **Workers** ➔ 点击 **Create Worker**；
4. 命名为 `wb-auth-gateway`（或任意名称）➔ 点击 **Deploy** (部署)；
5. 部署完成后，点击 **Edit code** (编辑代码)。

### 步骤 2：粘贴核心代码
1. 将本项目中 [`cloud/worker.js`](./worker.js) 的全部内容复制；
2. 粘贴替换网页编辑器中的全部默认代码；
3. 点击右上角 **Deploy** (保存并部署)。

### 步骤 3：创建并绑定 KV 数据库 (用于持久化授权)
1. 返回 Cloudflare 左侧菜单，展开 **Storage & Databases** ➔ 点击 **KV**；
2. 点击 **Create namespace** (创建命名空间)，名称输入：`WB_LICENSES` ➔ 点击 **Add**；
3. 返回进入刚创建的 `wb-auth-gateway` Worker ➔ 点击 **Settings** (设置) 选项卡 ➔ 点击 **Variables** (变量)；
4. 滚动到 **KV Namespace Bindings** 区域 ➔ 点击 **Add binding**：
   - **Variable name (变量名)** 必须填写：`WB_LICENSES`
   - **KV namespace (选择命名空间)** 下拉选择刚刚创建的 `WB_LICENSES`
5. （可选）在 **Environment Variables** (环境变量) 中添加：
   - **Variable name**: `ADMIN_SECRET`
   - **Value**: 您的自定义管理密码（默认是 `WB-ADMIN-SECRET-2026`）
6. 点击 **Deploy** 保存生效！

---

## 极速部署方式二：使用 Wrangler CLI 命令行部署

若您本地装有 Node.js，可在 `cloud/` 目录下直接终端一键发布：

```bash
# 1. 安装 Wrangler
npm install -g wrangler

# 2. 登录 Cloudflare 账号
wrangler login

# 3. 创建 KV 命名空间
wrangler kv:namespace create WB_LICENSES

# 4. 将生成的 id 填入 wrangler.toml，然后发布
wrangler deploy
```

---

## 访问与管理说明

部署完成后，Cloudflare 会为您生成一个全球唯一的免费域名，例如：
`https://wb-auth-gateway.<your-username>.workers.dev`

### 1. 访问可视化 Web 商业看板
在任何电脑或手机浏览器打开：
`https://wb-auth-gateway.<your-username>.workers.dev/admin?key=WB-ADMIN-SECRET-2026`
- 即可实时查看全网客户激活状态、机器码、累计搬家上架件数；
- 随时点击 **【封禁】**、**【解封】**、**【+30天】**、**【+1年】** 实行远程控制！

### 2. 客户端配置
在客户端的 `config.json` 或环境变量中配置您的云端网关地址：
```json
{
  "cloud_auth_url": "https://wb-auth-gateway.<your-username>.workers.dev"
}
```
客户端每次启动或上架时，会自动连线云端校验；一旦被管理员在 Web 控制台封禁，客户端下一秒立即闪退锁死！
