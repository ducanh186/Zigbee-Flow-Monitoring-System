# Setup Mosquitto Broker cho LAN
# Chạy script này với quyền Administrator

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Mosquitto LAN Setup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Kiểm tra Mosquitto đã cài chưa
Write-Host "[1] Checking Mosquitto installation..." -ForegroundColor Yellow
$mosquittoPath = "C:\Program Files\mosquitto\mosquitto.exe"
if (-not (Test-Path $mosquittoPath)) {
    Write-Host "❌ Mosquitto not found at: $mosquittoPath" -ForegroundColor Red
    Write-Host "Please install Mosquitto first: https://mosquitto.org/download/" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ Mosquitto found" -ForegroundColor Green
Write-Host ""

# 2. Tạo thư mục persistence
Write-Host "[2] Creating persistence directory..." -ForegroundColor Yellow
$persistDir = "mosquitto_data"
if (-not (Test-Path $persistDir)) {
    New-Item -ItemType Directory -Path $persistDir | Out-Null
    Write-Host "✓ Created: $persistDir" -ForegroundColor Green
} else {
    Write-Host "✓ Directory exists: $persistDir" -ForegroundColor Green
}
Write-Host ""

# 3. Mở Firewall cho port 1883
Write-Host "[3] Configuring Windows Firewall..." -ForegroundColor Yellow
$ruleName = "Mosquitto MQTT Broker (TCP 1883)"

# Xóa rule cũ nếu có
Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

# Tạo rule mới
try {
    New-NetFirewallRule -DisplayName $ruleName `
                        -Direction Inbound `
                        -Protocol TCP `
                        -LocalPort 1883 `
                        -Action Allow `
                        -Profile Private,Domain `
                        -Enabled True | Out-Null
    Write-Host "✓ Firewall rule added: $ruleName" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to add firewall rule. Run as Administrator!" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 4. Lấy IP của máy
Write-Host "[4] Network Information:" -ForegroundColor Yellow
$ipAddress = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress

if ($ipAddress) {
    Write-Host "   Local IP: $ipAddress" -ForegroundColor Cyan
    Write-Host "   MQTT URL: mqtt://$ipAddress:1883" -ForegroundColor Cyan
} else {
    Write-Host "   ⚠ Could not detect IP address" -ForegroundColor Yellow
}
Write-Host ""

# 5. Kiểm tra port 1883
Write-Host "[5] Checking if port 1883 is in use..." -ForegroundColor Yellow
$portInUse = Get-NetTCPConnection -LocalPort 1883 -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "⚠ Port 1883 is already in use:" -ForegroundColor Yellow
    $portInUse | Format-Table -Property LocalAddress, LocalPort, State, OwningProcess
    Write-Host ""
    $processId = $portInUse[0].OwningProcess
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "   Process: $($process.Name) (PID: $processId)" -ForegroundColor Cyan
        $answer = Read-Host "   Kill this process? (y/n)"
        if ($answer -eq 'y') {
            Stop-Process -Id $processId -Force
            Write-Host "   ✓ Process killed" -ForegroundColor Green
            Start-Sleep -Seconds 2
        }
    }
}
} else {
    Write-Host "✓ Port 1883 is available" -ForegroundColor Green
}
Write-Host ""

# 6. Hướng dẫn chạy broker
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Start broker with LAN config:" -ForegroundColor White
Write-Host "   mosquitto -c mosquitto.conf -v" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. On remote machine (Máy B), connect to:" -ForegroundColor White
if ($ipAddress) {
    Write-Host "   MQTT_HOST=$ipAddress" -ForegroundColor Cyan
} else {
    Write-Host "   MQTT_HOST=<YOUR_IP_HERE>" -ForegroundColor Cyan
}
Write-Host "   MQTT_PORT=1883" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Test connection from remote machine:" -ForegroundColor White
if ($ipAddress) {
    Write-Host "   mosquitto_sub -h $ipAddress -t 'test/#' -v" -ForegroundColor Cyan
} else {
    Write-Host "   mosquitto_sub -h <YOUR_IP> -t 'test/#' -v" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
