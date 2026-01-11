# Quick Start Script - Mosquitto Broker for LAN
# Chạy broker với config cho phép kết nối từ LAN

$configFile = "mosquitto.conf"

# Kiểm tra config file
if (-not (Test-Path $configFile)) {
    Write-Host "❌ Config file not found: $configFile" -ForegroundColor Red
    Write-Host "Please run setup_mosquitto_lan.ps1 first!" -ForegroundColor Yellow
    exit 1
}

# Lấy IP
$ipAddress = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { 
    $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*" 
} | Select-Object -First 1).IPAddress

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting Mosquitto Broker (LAN Mode)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Listening on: 0.0.0.0:1883" -ForegroundColor Green
if ($ipAddress) {
    Write-Host "LAN Address: mqtt://$ipAddress:1883" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Chạy mosquitto
& "C:\Program Files\mosquitto\mosquitto.exe" -c $configFile -v
