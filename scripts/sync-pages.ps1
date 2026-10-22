<#
    同步前端静态文件到 GitHub Pages 部署仓库

    背景：GitHub Pages 的发布源只支持仓库根目录或 /docs，不能直接发布 /web，
    因此另建一个专用部署仓库存放 web/ 下的静态文件。本脚本负责把主仓库的
    前端文件复制过去并推送，触发 Actions 自动发布。

    用法：
        .\sync-pages.ps1
        .\sync-pages.ps1 -DeployDir "C:\soft\opencode_download\deploy-uestc-web"
        .\sync-pages.ps1 -SkipPush      # 只复制不推送
#>
param(
    # 部署仓库本地路径
    [string]$DeployDir = "C:\soft\opencode_download\deploy-uestc-web",
    # 只复制不推送
    [switch]$SkipPush
)

# 注意：git 会把 LF/CRLF 警告写到 stderr，这里不能因警告中断脚本
$ErrorActionPreference = "Continue"

# 定位项目根目录（脚本所在目录的上级）
$projectRoot = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $projectRoot "web"

if (-not (Test-Path $webDir)) {
    Write-Host "[错误] 找不到前端目录：$webDir" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $DeployDir)) {
    Write-Host "[错误] 找不到部署仓库目录：$DeployDir" -ForegroundColor Red
    exit 1
}

Write-Host "[信息] 主仓库前端：$webDir" -ForegroundColor Cyan
Write-Host "[信息] 部署仓库：$DeployDir" -ForegroundColor Cyan

# 复制 index.html 与 web 下的其他静态资源
Copy-Item (Join-Path $webDir "index.html") -Destination (Join-Path $DeployDir "index.html") -Force

Get-ChildItem -Path $webDir -File | Where-Object { $_.Name -ne "index.html" } | ForEach-Object {
    Write-Host "[信息] 复制静态资源：$($_.Name)" -ForegroundColor Cyan
    Copy-Item $_.FullName -Destination (Join-Path $DeployDir $_.Name) -Force
}

Push-Location $DeployDir
try {
# 统一按 LF 存储，避免每次提交都出现换行符转换警告
git config core.autocrlf false 2>&1 | Out-Null

    # 包装 git 调用：把 stderr 合并进 stdout，避免 PowerShell 把警告误判为错误
    # 参数以数组传入，防止 -A、-m 等被 PowerShell 当成参数名解析
    function Invoke-Git {
        param([string[]]$GitArgs)
        $output = & git @GitArgs 2>&1
        $code = $LASTEXITCODE
        if ($output) { $output | ForEach-Object { Write-Host "    $_" } }
        return $code
    }

    $code = Invoke-Git @("add", "-A")
    if ($code -ne 0) { Write-Host "[错误] git add 失败（退出码 $code）" -ForegroundColor Red; exit 1 }

    $staged = git diff --cached --name-only 2>$null
    if (-not $staged) {
        Write-Host "[信息] 前端无变化，无需推送" -ForegroundColor Yellow
        exit 0
    }

    Write-Host "[信息] 待提交文件：" -ForegroundColor Cyan
    $staged | ForEach-Object { Write-Host "    $_" }

    $code = Invoke-Git @("commit", "-m", "chore: 同步主仓库前端到 Pages 部署仓库")
    if ($code -ne 0) {
        Write-Host "[错误] 提交失败（退出码 $code）" -ForegroundColor Red
        exit 1
    }
    Write-Host "[成功] 已提交" -ForegroundColor Green

    if ($SkipPush) {
        Write-Host "[信息] 已跳过推送（-SkipPush）" -ForegroundColor Yellow
    } else {
        $code = Invoke-Git @("push")
        if ($code -ne 0) {
            Write-Host "[错误] 推送失败（退出码 $code）" -ForegroundColor Red
            exit 1
        }
        Write-Host "[成功] 已推送，Actions 将自动发布到 GitHub Pages" -ForegroundColor Green
    }
}
finally {
    Pop-Location
}
