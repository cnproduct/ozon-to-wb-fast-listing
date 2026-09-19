---
name: wb-learning-client-bootstrap
description: 在新 Windows 电脑安装 WB Skill 学习客户端与 Antigravity 自动同步。适用于缺少 Git、Python 或已有旧版全局 Skill 的设备；运行随附 PowerShell 安装器并让用户在本机粘贴管理员签发的设备令牌。
---

# WB 学习客户端 Windows 安装

当用户要求在 Windows 上安装或修复 WB Skill 学习客户端时，运行同目录的 [安装器](scripts/install-wb-learning-client.ps1)。安装器面向 64 位 Windows，使用现有的 Antigravity 安装；它会检查 Git/Python、更新官方仓库、配置当前 Windows 用户的设备令牌、安装 Antigravity 规则同步与 Skill 更新 sidecar，并检查最终状态。

在新电脑上双击文件夹中的 `install.cmd`，或在 Windows PowerShell 中执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<本 Skill 目录>\scripts\install-wb-learning-client.ps1"
```

若脚本以压缩包交付，先解压，再从解压目录执行。只从可信的本地副本运行；不要从聊天消息里执行临时拼接的下载命令。

令牌由用户在 PowerShell 隐藏输入提示处粘贴。不要要求用户把令牌发到聊天，不要把它放在命令行参数、Skill 文件、脚本、日志或 Git 仓库。看到 `PS ...>` 提示符时不要单独粘贴令牌，那表示安装器已经退出。安装失败时报告具体步骤和非敏感错误；不把 Git/Python 检查通过当作整个安装完成。

安装器仅安装学习规则同步与 WB Skill，不签发商业授权、不绑定 Wildberries 店铺，也不执行商品上架。安装后如需这些业务操作，走原有 WB Skill 的授权流程。
