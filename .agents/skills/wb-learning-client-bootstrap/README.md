# WB 学习客户端 Windows 一键安装

在新的 64 位 Windows 电脑上安装 WB Skill 的学习规则同步与 Antigravity 自动更新。需要先安装 Antigravity，并准备管理员签发的 **43 位设备令牌**。设备令牌与 WB 店铺商业授权不同。

本安装器也已内置在 [WB Fast Listing 主仓库](https://github.com/cnproduct/ozon-to-wb-fast-listing)及其受保护下载包中；从主仓库下载时，可直接双击根目录的 `install-wb-learning-client.cmd`。

## 直接运行

1. 在本仓库页面选择 **Code → Download ZIP**，解压到本机。
2. 双击解压目录中的 `install.cmd`。
3. 安装器提示时，只粘贴设备令牌文本；输入不会显示。不要在 `PS C:\...>` 命令提示符后单独粘贴令牌。
4. 看到“安装完成”后重启 Antigravity。

安装器会检测并安装缺失的 Git/Python，从 `cnproduct/ozon-to-wb-fast-listing` 获取主分支，配置当前 Windows 用户的设备令牌、规则同步和每日 Skill 更新。旧版非 Git 管理的全局 WB Skill 会先移入 `~\.codex\wb-skill-learning\backups\`。已有仓库若包含本地改动，安装器会停止，以免覆盖文件。

## 在 Antigravity 中运行

把本仓库文件夹放入 `%USERPROFILE%\.gemini\config\skills\wb-learning-client-bootstrap`，然后在 Antigravity 对话中要求运行 `wb-learning-client-bootstrap`。复制 Skill 文件夹本身不会自动执行脚本；令牌只在本机 PowerShell 的隐藏输入提示中粘贴，不发到聊天窗口。

安装器使用官方来源的 Git、Python 安装包，并在运行前检查 Windows 数字签名。脚本以 UTF-8 BOM 保存，兼容 Windows PowerShell 5.1。安装完成会检查 `skill-update-status.json` 与全局 Skill 文件。安装器不负责安装 Antigravity 应用本身，也不签发商业授权、绑定店铺或执行商品上架。

## 常见问题与排查指南

### 1. 设备令牌格式与输入技巧
- **严格 43 位格式**：设备专属令牌（Device Ingest Token）仅包含大小写英文字母、数字、下划线 `_` 与减号 `-`（正则：`^[A-Za-z0-9_-]{43}$`）。
- **请勿包含前后杂质**：请勿复制诸如 `令牌：`、`token=` 等文字标签，也不要复制 PowerShell 提示符（如 `PS C:\...>`）。
- **与店铺 API 令牌区分**：设备令牌用于学习规则云端同步通道，**不是** Wildberries 店铺后台生成的长串 JWT API 密钥（`eyJ...` 开头），也**不是**商业店铺授权码。
- **安全输入不回显**：终端提示输入令牌时，直接右键单击或按 `Ctrl+V` 粘贴并回车即可。出于安全保护，屏幕不会显示任何星号或字符。

### 2. 幂等执行与重复运行保障
- 安装脚本已通过 `Set-StrictMode -Version Latest` 严苛模式适配。
- 支持在已克隆仓库的情况下安全重复重跑；工作区无任何本地改动时自动快进合并（`merge --ff-only`），绝不抛出 Null 对象调用异常。

### 3. 安装完成验证
安装完成后可查看本地状态配置验证就绪状态：
- 配置文件：`%USERPROFILE%\.codex\wb-skill-learning\hub-config.json`
- 状态记录：`%USERPROFILE%\.codex\wb-skill-learning\skill-update-status.json`（其中 `status` 字段应为 `ok`）
- 看到“安装完成”后，请**完全退出并重启 Antigravity**以加载最新的受管 Skill 与后台更新服务。
