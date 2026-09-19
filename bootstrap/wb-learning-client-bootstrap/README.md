# WB Fast Listing 内置 Windows 学习客户端安装

在新的 64 位 Windows 电脑上安装 WB Skill 的学习规则同步与 Antigravity 自动更新。需要先安装 Antigravity，并准备管理员签发的 **43 位设备令牌**。设备令牌与 WB 店铺商业授权不同。

## 直接运行

1. 在 `cnproduct/ozon-to-wb-fast-listing` 仓库页面选择 **Code → Download ZIP**，解压到本机。
2. 双击仓库根目录的 `install-wb-learning-client.cmd`，或双击本目录的 `install.cmd`。
3. 安装器提示时，只粘贴设备令牌文本；输入不会显示。不要在 `PS C:\...>` 命令提示符后单独粘贴令牌。
4. 看到“安装完成”后重启 Antigravity。

安装器会检测并安装缺失的 Git/Python，从 `cnproduct/ozon-to-wb-fast-listing` 获取主分支，配置当前 Windows 用户的设备令牌、规则同步和每日 Skill 更新。旧版非 Git 管理的全局 WB Skill 会先移入 `~\.codex\wb-skill-learning\backups\`。已有仓库若包含本地改动，安装器会停止，以免覆盖文件。

## 在 Antigravity 中运行

如果已把 WB Fast Listing 仓库放入 Antigravity 的全局 Skill 目录，在对话中要求 `ozon-to-wb-fast-listing` 运行 `bootstrap/wb-learning-client-bootstrap/scripts/install-wb-learning-client.ps1`。复制文件夹本身不会自动执行脚本；令牌只在本机 PowerShell 的隐藏输入提示中粘贴，不发到聊天窗口。

安装器使用官方来源的 Git、Python 安装包，并在运行前检查 Windows 数字签名。脚本以 UTF-8 BOM 保存，兼容 Windows PowerShell 5.1。安装完成会检查 `skill-update-status.json` 与全局 Skill 文件。安装器不负责安装 Antigravity 应用本身，也不签发商业授权、绑定店铺或执行商品上架。
