# 分卷压缩全量爬取数据
$sourceDir = "C:\soft\opencode_download\uestc-public-full\posts"
$outputDir = "C:\soft\opencode_download\uestc-full-compressed"
$maxSizeMB = 45

# 创建输出目录
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$files = Get-ChildItem -Path $sourceDir -Filter "thread_*.json" | Sort-Object Name
$totalSize = ($files | Measure-Object -Property Length -Sum).Sum
Write-Host "总文件数: $($files.Count)"
Write-Host "总大小: $([math]::Round($totalSize / 1MB, 2)) MB"

$partNum = 1
$currentSize = 0
$currentFiles = @()
$fileCount = 0

foreach ($file in $files) {
    $fileCount++
    
    if (($currentSize + $file.Length) -gt ($maxSizeMB * 1024 * 1024) -and $currentFiles.Count -gt 0) {
        # 创建当前部分的压缩包
        $archiveName = Join-Path $outputDir "uestc-posts-part$partNum.zip"
        Write-Host "创建: $archiveName ($($currentFiles.Count) 个文件, $([math]::Round($currentSize / 1MB, 2)) MB)"
        Compress-Archive -Path $currentFiles -DestinationPath $archiveName -CompressionLevel Optimal
        
        $partNum++
        $currentSize = 0
        $currentFiles = @()
    }
    
    $currentSize += $file.Length
    $currentFiles += $file.FullName
    
    # 显示进度
    if ($fileCount % 10000 -eq 0) {
        Write-Host "进度: $fileCount / $($files.Count) ($([math]::Round($fileCount * 100 / $files.Count, 1))%)"
    }
}

# 创建最后一部分
if ($currentFiles.Count -gt 0) {
    $archiveName = Join-Path $outputDir "uestc-posts-part$partNum.zip"
    Write-Host "创建: $archiveName ($($currentFiles.Count) 个文件, $([math]::Round($currentSize / 1MB, 2)) MB)"
    Compress-Archive -Path $currentFiles -DestinationPath $archiveName -CompressionLevel Optimal
}

Write-Host "`n完成! 共创建 $partNum 个分卷压缩包"
Write-Host "输出目录: $outputDir"