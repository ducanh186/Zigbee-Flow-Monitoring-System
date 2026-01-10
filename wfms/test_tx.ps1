# TX Test Script
# Run this AFTER starting gateway in another terminal

Write-Host "`n=== TX Test Script ===" -ForegroundColor Cyan
Write-Host "Make sure Gateway is running: python -m gateway.service --uart COM10 --debug" -ForegroundColor Yellow

$baseUrl = "http://127.0.0.1:8080"
$mosquitto = "C:\Program Files\mosquitto"

# Check gateway is running
Write-Host "`n[1] Checking Gateway health..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 2
    Write-Host "  ✓ Gateway is UP (uptime: $($health.uptime_s)s)" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Gateway is DOWN! Start it first." -ForegroundColor Red
    Write-Host "  Run: Set-Location wfms; python -m gateway.service --uart COM10 --debug" -ForegroundColor Yellow
    exit 1
}

# Send valve ON command
Write-Host "`n[2] Sending valve ON command..." -ForegroundColor Yellow
$cid = "tx_test_$(Get-Random -Maximum 9999)"
$cmd = @{
    cid = $cid
    value = "ON"
    by = "test_script"
    ts = [int][double]::Parse((Get-Date -UFormat %s))
} | ConvertTo-Json -Compress

Write-Host "  Command: $cmd"
Write-Host "  CID: $cid"

# Publish command
$cmdFile = [System.IO.Path]::GetTempFileName()
$cmd | Out-File -FilePath $cmdFile -Encoding UTF8 -NoNewline
& "$mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -f $cmdFile
Remove-Item $cmdFile

Write-Host "  ✓ Command published" -ForegroundColor Green

# Wait and check logs
Write-Host "`n[3] Waiting 4s for ACK..." -ForegroundColor Yellow
Start-Sleep -Seconds 4

# Get recent logs from Admin API
Write-Host "`n[4] Checking Gateway logs..." -ForegroundColor Yellow
try {
    $logs = Invoke-RestMethod -Uri "$baseUrl/logs?limit=20"
    Write-Host "  Recent logs:" -ForegroundColor Cyan
    foreach ($log in $logs.logs) {
        if ($log.message -like "*$cid*" -or $log.message -like "*TX*" -or $log.message -like "*ACK*" -or $log.message -like "*Received command*") {
            Write-Host "  [$($log.level)] $($log.message)"
        }
    }
} catch {
    Write-Host "  Could not get logs: $_" -ForegroundColor Red
}

# Summary
Write-Host "`n=== Expected Results ===" -ForegroundColor Cyan
Write-Host "Mức 1 (TX OK): Gateway should log 'TX >>> @CMD {\"id\":1,\"op\":\"valve_set\",\"value\":\"open\"}'" -ForegroundColor Yellow
Write-Host "Mức 2 (ACK OK): Gateway should log 'Published ACK: cid=$cid, ok=True'" -ForegroundColor Yellow
Write-Host "Mức 3 (State Change): Check wfms/lab1/state for valve='ON'" -ForegroundColor Yellow

Write-Host "`nCheck Gateway terminal for detailed logs!" -ForegroundColor Magenta
