# 分卷压缩爬取数据
$sourceDir = "C:\soft\opencode_download\uestc-public-20260918\posts"
$outputDir = "C:\soft\opencode_download"
$maxSizeMB = 45

$files = Get-ChildItem -Path $sourceDir -Filter "thread_*.json" | Sort-Object Name
$totalSize = ($files | Measure-Object -Property Length -Sum).Sum
$partNum = 1
$currentSize = 0
$currentFiles = @()

foreach ($file in $files) {
    if (($currentSize + $file.Length) -gt ($maxSizeMB * 1024 * 1024) -and $currentFiles.Count -gt 0) {
        # 创建当前部分的压缩包
        $archiveName = Join-Path $outputDir "uestc-posts-20260918-part$partNum.zip"
        Compress-Archive -Path $currentFiles -DestinationPath $archiveName -CompressionLevel Optimal
        Write-Host "创建: $archiveName ($([math]::Round((Get-Item $archiveName).Length / 1MB, 2)) MB)"
        
        $partNum++
        $currentSize = 0
        $currentFiles = @()
    }
    
    $currentSize += $file.Length
    $currentFiles += $file.FullName
}

# 创建最后一部分
if ($currentFiles.Count -gt 0) {
    $archiveName = Join-Path $outputDir "uestc-posts-20260918-part$partNum.zip"
    Compress-Archive -Path $currentFiles -DestinationPath $archiveName -CompressionLevel Optimal
    Write-Host "创建: $archiveName ($([math]::Round((Get-Item $archiveName).Length / 1MB, 2)) MB)"
}

Write-Host "完成! 共创建 $partNum 个分卷压缩包"