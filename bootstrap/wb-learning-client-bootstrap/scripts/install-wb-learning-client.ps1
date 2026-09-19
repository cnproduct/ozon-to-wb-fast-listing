#requires -Version 5.1
<#
Run from Windows PowerShell:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-wb-learning-client.ps1
The device token is requested interactively and is never accepted as a command-line argument.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repository = 'https://github.com/cnproduct/ozon-to-wb-fast-listing.git'
$repoDirectory = Join-Path $HOME 'ozon-to-wb-fast-listing'
$learningDirectory = Join-Path $HOME '.codex\wb-skill-learning'
$configPath = Join-Path $learningDirectory 'hub-config.json'
$skillDirectory = Join-Path $HOME '.gemini\config\skills\ozon-to-wb-fast-listing'
$endpoint = 'https://wb-skill-learning-hub.cnproduct.workers.dev'

# A copied WB Skill may contain this installer inside the directory that must be
# backed up. Run from a temporary copy and leave that directory before moving it.
if ($PSCommandPath) {
    $activeScript = [IO.Path]::GetFullPath($PSCommandPath)
    $targetPrefix = [IO.Path]::GetFullPath($skillDirectory).TrimEnd('\') + '\'
    if ($activeScript.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        $stagedScript = Join-Path $env:TEMP ('wb-learning-bootstrap-' + [guid]::NewGuid().ToString('N') + '.ps1')
        Copy-Item -LiteralPath $activeScript -Destination $stagedScript
        Set-Location $HOME
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stagedScript
            exit $LASTEXITCODE
        } finally {
            Remove-Item -LiteralPath $stagedScript -Force -ErrorAction SilentlyContinue
        }
    }
}

function Step([string]$message) { Write-Host "[WB 安装] $message" }
function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user;$env:Path"
}
function Find-Executable([string]$name, [string[]]$locations) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command -and $command.Source) { return $command.Source }
    foreach ($location in $locations) {
        if ($location -and (Test-Path -LiteralPath $location -PathType Leaf)) { return $location }
    }
    return $null
}
function Download-VerifiedInstaller([string]$url, [string]$file) {
    Step "下载官方安装包：$([IO.Path]::GetFileName($file))"
    Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
    $signature = Get-AuthenticodeSignature -LiteralPath $file
    if ($signature.Status -ne 'Valid') { throw "安装包签名无效：$($signature.Status)" }
}
function Run-Installer([string]$file, [string[]]$arguments) {
    $process = Start-Process -FilePath $file -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) { throw "安装程序失败，退出码 $($process.ExitCode)" }
    Refresh-Path
}
function Get-Python {
    $candidates = @(
        (Find-Executable 'python.exe' @()),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:ProgramFiles 'Python313\python.exe')
    ) | Where-Object { $_ }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        try {
            $version = & $candidate -c 'import sys; print(int(sys.version_info >= (3, 10)))' 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -eq '1') { return $candidate }
        } catch { continue }
    }
    return $null
}
function Invoke-Git([string[]]$arguments) {
    & $script:git @arguments
    if ($LASTEXITCODE -ne 0) { throw "Git 命令失败：$($arguments[0])" }
}
function Save-DeviceToken {
    param([switch]$Force)
    if (-not $Force -and (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        try {
            $existing = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($existing.endpoint -eq $endpoint -and $existing.ingest_token -cmatch '^[A-Za-z0-9_-]{43}$') {
                Step '检测到当前用户已有设备令牌配置。'
                return
            }
        } catch { }
    }
    New-Item -ItemType Directory -Path $learningDirectory -Force | Out-Null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $secure = Read-Host '请粘贴管理员签发的 43 位设备令牌（输入不会显示）' -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim() }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        try {
            if ($token -cnotmatch '^[A-Za-z0-9_-]{43}$') {
                Write-Warning "格式无效（第 $attempt/3 次）。请只复制令牌文本，不要复制 PS 提示符或整段命令。"
                continue
            }
            $payload = @{ endpoint = $endpoint; ingest_token = $token } | ConvertTo-Json
            $temporary = Join-Path $learningDirectory ([IO.Path]::GetRandomFileName())
            try {
                [IO.File]::WriteAllText($temporary, $payload, [Text.UTF8Encoding]::new($false))
                Move-Item -LiteralPath $temporary -Destination $configPath -Force
            } finally {
                if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
            }
            try {
                if ((Get-Clipboard -Raw -ErrorAction Stop).Trim() -ceq $token) { Set-Clipboard -Value ' ' }
            } catch { }
            Step '设备令牌已保存到当前用户配置。'
            return
        } finally { $token = $null; $secure = $null }
    }
    throw '三次输入均无效；请重新运行安装器。'
}
function Backup-UnmanagedSkill {
    if (-not (Test-Path -LiteralPath $skillDirectory)) { return }
    $item = Get-Item -LiteralPath $skillDirectory -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "全局 Skill 是链接，已停止以免移动链接指向的内容：$skillDirectory"
    }
    if (Test-Path -LiteralPath (Join-Path $skillDirectory '.git')) { return }
    $backupRoot = Join-Path $learningDirectory 'backups'
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backup = Join-Path $backupRoot ('ozon-to-wb-fast-listing-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6))
    Move-Item -LiteralPath $skillDirectory -Destination $backup -ErrorAction Stop
    Step "已备份旧版全局 Skill：$backup"
}
function Enable-Utf8Sidecars {
    foreach ($name in @('wb-skill-rules-sync', 'wb-skill-auto-update')) {
        $path = Join-Path $HOME ".gemini\config\sidecars\$name\sidecar.json"
        $sidecar = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        $arguments = @($sidecar.args)
        if ($arguments.Count -lt 3) { throw "sidecar 参数不完整：$name" }
        if ($arguments[2] -ne '-X') {
            $sidecar.args = @($arguments[0], $arguments[1], '-X', 'utf8') + @($arguments[2..($arguments.Count - 1)])
            [IO.File]::WriteAllText($path, ($sidecar | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
        }
    }
}

try {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw '需要 64 位 Windows。' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Refresh-Path
    $gitLocations = @((Join-Path $env:ProgramFiles 'Git\cmd\git.exe'), (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe'))
    $git = Find-Executable 'git.exe' $gitLocations
    if (-not $git) {
        $setup = Join-Path $env:TEMP 'Git-2.55.0.5-64-bit.exe'
        Download-VerifiedInstaller 'https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/Git-2.55.0.5-64-bit.exe' $setup
        Run-Installer $setup @('/VERYSILENT', '/NORESTART', '/NOCANCEL', '/SP-', '/CURRENTUSER', "/DIR=`"$env:LOCALAPPDATA\Programs\Git`"")
        $git = Find-Executable 'git.exe' $gitLocations
        if (-not $git) { throw 'Git 安装后仍无法找到 git.exe。' }
    }
    Step "Git 就绪：$(& $git --version)"
    $python = Get-Python
    if (-not $python) {
        $setup = Join-Path $env:TEMP 'python-3.13.15-amd64.exe'
        Download-VerifiedInstaller 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe' $setup
        Run-Installer $setup @('/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1', 'InstallLauncherAllUsers=0', 'Include_test=0')
        $python = Get-Python
        if (-not $python) { throw 'Python 安装后仍无法找到 Python 3.10+。' }
    }
    Step "Python 就绪：$(& $python --version)"
    if ((Test-Path -LiteralPath $repoDirectory) -and
        -not (Test-Path -LiteralPath (Join-Path $repoDirectory '.git'))) {
        $bundleRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
        if ($bundleRoot -ieq [IO.Path]::GetFullPath($repoDirectory) -and
            -not (Test-Path -LiteralPath (Join-Path $repoDirectory 'scripts\install_learning_rule_sync.py'))) {
            $repoDirectory = Join-Path $HOME 'ozon-to-wb-fast-listing-managed-source'
            Step '发布包不含学习同步源码，改从官方仓库取得安装脚本。'
        }
    }
    if (-not (Test-Path -LiteralPath $repoDirectory)) {
        Invoke-Git @('clone', '--branch', 'main', '--single-branch', $repository, $repoDirectory)
    } else {
        if (-not (Test-Path -LiteralPath (Join-Path $repoDirectory '.git'))) {
            $bundleRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
            if ($bundleRoot -ine [IO.Path]::GetFullPath($repoDirectory) -or
                -not (Test-Path -LiteralPath (Join-Path $repoDirectory 'scripts\install_learning_rule_sync.py'))) {
                throw "现有目录不是 Git 仓库：$repoDirectory"
            }
            Step '使用当前已解压的 WB Skill 文件。'
        } else {
            $remote = (& $git -C $repoDirectory remote get-url origin).Trim()
            if ($LASTEXITCODE -ne 0 -or $remote -notin @($repository, 'https://github.com/cnproduct/ozon-to-wb-fast-listing')) { throw '现有仓库来源不匹配，已停止。' }
            $branch = (& $git -C $repoDirectory branch --show-current).Trim()
            if ($branch -ne 'main') { throw "现有仓库分支不是 main：$branch" }
            $dirty = (& $git -C $repoDirectory status --porcelain).Trim()
            if ($dirty) { throw '现有仓库有本地改动，已停止以免覆盖。' }
            Invoke-Git @('-C', $repoDirectory, 'fetch', '--quiet', 'origin', 'main')
            Invoke-Git @('-C', $repoDirectory, 'merge', '--ff-only', 'origin/main')
        }
    }
    foreach ($name in @('sync_learning_rules.py', 'install_learning_rule_sync.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $repoDirectory "scripts\$name"))) { throw "官方仓库缺少脚本：$name" }
    }
    Save-DeviceToken
    $env:PYTHONUTF8 = '1'
    Step '验证令牌并同步已发布规则...'
    & $python -X utf8 (Join-Path $repoDirectory 'scripts\sync_learning_rules.py')
    if ($LASTEXITCODE -ne 0) {
        Write-Warning '同步失败。请重新粘贴令牌；若再次失败，请检查网络或联系管理员。'
        Save-DeviceToken -Force
        & $python -X utf8 (Join-Path $repoDirectory 'scripts\sync_learning_rules.py')
        if ($LASTEXITCODE -ne 0) { throw '令牌验证或规则同步失败；请核对令牌和网络。' }
    }
    Backup-UnmanagedSkill
    Step '安装 Antigravity sidecar 与受管 Skill...'
    & $python -X utf8 (Join-Path $repoDirectory 'scripts\install_learning_rule_sync.py')
    if ($LASTEXITCODE -ne 0) { throw 'Antigravity sidecar 安装失败。' }
    Enable-Utf8Sidecars
    $statusPath = Join-Path $learningDirectory 'skill-update-status.json'
    if (-not (Test-Path -LiteralPath $statusPath)) { throw '缺少 Skill 更新状态文件。' }
    $status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($status.status -ne 'ok') { throw 'Skill 更新状态不是 ok。' }
    if (-not (Test-Path -LiteralPath (Join-Path $skillDirectory 'SKILL.md'))) { throw '全局 Skill 未安装完整。' }
    Step "安装完成。Skill commit：$($status.commit)"
    Step '如果 Antigravity 已打开，请重启以加载新的 Skill 和 sidecar。'
} catch {
    Write-Error "WB 学习客户端安装未完成：$($_.Exception.Message)"
    exit 1
}
