<#
.SYNOPSIS
  知识库增量更新流水线：爬取新帖 -> 预处理 -> 分块 -> 向量入库 -> FTS 入库

.DESCRIPTION
  每步通过 -Skip* 开关可跳过；全部成功后打印「重启服务」提示
  （uvicorn 无 --reload，需手动重启才能加载新数据）。

  用法示例：
    .\run-update.ps1                          # 全流程（需 BBS_USER/BBS_PASS 环境变量）
    .\run-update.ps1 -SkipCrawl -SkipEmbed    # 只重建 FTS
    .\run-update.ps1 -MinTid 2400000          # 指定基准 tid（默认从增量抓取报告读取）
#>
param(
    [string]$PostsDir = "C:\soft\opencode_download\uestc-public-full\posts",
    [string]$Python = "C:\soft\python\python.exe",
    [string]$KbDir = "$PSScriptRoot",
    [int]$MinTid = 0,
    [switch]$SkipCrawl,
    [switch]$SkipPreprocess,
    [switch]$SkipEmbed,
    [switch]$SkipFts
)

$ErrorActionPreference = "Stop"
$KbDir = (Resolve-Path $KbDir).Path
$Crawler = Join-Path $KbDir "..\crawler\uestc_bbs_crawler.py"
$ProcessedDir = Join-Path $KbDir "processed"
$ChunksJsonl = Join-Path $ProcessedDir "chunks.jsonl"
$ReportFile = Join-Path $PostsDir "_incremental_report.json"

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "`n===== $Name =====" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "步骤失败: $Name（退出码 $LASTEXITCODE）" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# 1. 增量抓取（模式 8），报告里记录 base_tid
if (-not $SkipCrawl) {
    if (-not $env:BBS_USER -or -not $env:BBS_PASS) {
        Write-Host "未设置 BBS_USER / BBS_PASS 环境变量，无法登录抓取" -ForegroundColor Red
        exit 1
    }
    Invoke-Step "增量抓取（爬虫模式 8）" {
        $env:BBS_MODE = "8"
        & $Python $Crawler --data-dir (Split-Path $PostsDir) --max-pages 3
    }
}

# 2. 确定基准 tid：优先命令行，其次抓取报告
if ($MinTid -eq 0) {
    if (Test-Path $ReportFile) {
        $MinTid = (Get-Content $ReportFile -Raw -Encoding UTF8 | ConvertFrom-Json).base_tid
        Write-Host "从增量报告读取基准 tid: $MinTid"
    } else {
        Write-Host "缺少增量报告且未指定 -MinTid，将按全量处理" -ForegroundColor Yellow
    }
}

# 3. 预处理 + 分块（全量重建，本地 CPU 操作很快）
if (-not $SkipPreprocess) {
    Invoke-Step "预处理" {
        & $Python (Join-Path $KbDir "preprocess.py") --input $PostsDir --output $ProcessedDir
    }
    Invoke-Step "分块" {
        & $Python (Join-Path $KbDir "chunk-data.py") `
            --input (Join-Path $ProcessedDir "knowledge_units.json") `
            --output $ChunksJsonl `
            --boards (Join-Path (Split-Path $PostsDir) "boards_list.json") `
            --threads (Join-Path (Split-Path $PostsDir) "threads")
    }
}

# 4. 向量增量入库（只 embed tid > 基准的新块，upsert 幂等）
if (-not $SkipEmbed) {
    Invoke-Step "向量增量入库" {
        $embedArgs = @("--input", $ChunksJsonl, "--db", (Join-Path $KbDir "chroma_db"))
        if ($MinTid -gt 0) { $embedArgs += @("--min-tid", $MinTid) }
        & $Python (Join-Path $KbDir "embed-index.py") @embedArgs
    }
}

# 5. FTS 增量入库（rowid 续接）
if (-not $SkipFts) {
    Invoke-Step "FTS 增量入库" {
        $ftsArgs = @("--input", $ChunksJsonl, "--db", (Join-Path $KbDir "fts_index.db"))
        if ($MinTid -gt 0) { $ftsArgs += @("--min-tid", $MinTid) }
        & $Python (Join-Path $KbDir "build-fts.py") @ftsArgs
    }
}

Write-Host "`n===== 增量更新完成 =====" -ForegroundColor Green
Write-Host "基准 tid: $MinTid"
Write-Host "下一步：重启 uvicorn 服务以加载新数据（服务无 --reload，不重启不生效）"
