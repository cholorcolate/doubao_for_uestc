$sourceDir = "C:\soft\opencode_download\uestc-public-full\posts"
$outputDir = "C:\soft\opencode_download\uestc-full-compressed"
$maxSizeMB = 45

$allFiles = Get-ChildItem -Path $sourceDir -Filter "thread_*.json" | Sort-Object Name
$existingParts = (Get-ChildItem -Path $outputDir -Filter "uestc-posts-part*.zip").Count
$filesPerPart = 10000
$startIndex = $existingParts * $filesPerPart

if ($startIndex -ge $allFiles.Count) {
    Write-Host "Done"
    return
}

$remainingFiles = $allFiles[$startIndex..($allFiles.Count - 1)]
$partNum = $existingParts + 1
$currentSize = 0
$currentFiles = @()

foreach ($file in $remainingFiles) {
    if (($currentSize + $file.Length) -gt ($maxSizeMB * 1024 * 1024) -and $currentFiles.Count -gt 0) {
        $archiveName = Join-Path $outputDir ("uestc-posts-part" + $partNum + ".zip")
        Compress-Archive -Path $currentFiles -DestinationPath $archiveName -CompressionLevel Optimal
        Write-Host ("Part " + $partNum + ": " + $currentFiles.Count + " files")
        $partNum++
        $currentSize = 0
        $currentFiles = @()
    }
    $currentSize += $file.Length
    $currentFiles += $file.FullName
}

if ($currentFiles.Count -gt 0) {
    $archiveName = Join-Path $outputDir ("uestc-posts-part" + $partNum + ".zip")
    Compress-Archive -Path $currentFiles -DestinationPath $archiveName -CompressionLevel Optimal
    Write-Host ("Part " + $partNum + ": " + $currentFiles.Count + " files")
}

Write-Host ("Total parts created: " + ($partNum - $existingParts))