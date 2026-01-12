# Restart Mosquitto Broker với config LAN
# Chạy script này với quyền Administrator

Write-Host "Stopping existing Mosquitto processes..." -ForegroundColor Yellow
Get-Process mosquitto -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

Write-Host "Starting Mosquitto with LAN config..." -ForegroundColor Yellow
Write-Host ""

# Kiểm tra config file
if (-not (Test-Path "mosquitto.conf")) {
    Write-Host "❌ mosquitto.conf not found!" -ForegroundColor Red
    exit 1
}

# Start broker
$mosquittoPath = "C:\Program Files\mosquitto\mosquitto.exe"
if (Test-Path $mosquittoPath) {
    Start-Process -FilePath $mosquittoPath -ArgumentList "-c", "mosquitto.conf", "-v" -NoNewWindow
    Start-Sleep -Seconds 2
    
    # Kiểm tra port
    Write-Host "Checking listening ports..." -ForegroundColor Yellow
    $listeners = netstat -ano | findstr ":1883.*LISTENING"
    if ($listeners) {
        Write-Host ""
        Write-Host "✓ Mosquitto is running:" -ForegroundColor Green
        $listeners | ForEach-Object { Write-Host "  $_" -ForegroundColor Cyan }
        
        # Kiểm tra có listen trên 0.0.0.0 không
        if ($listeners -match "0\.0\.0\.0:1883") {
            Write-Host ""
            Write-Host "✓ Broker is accessible from LAN!" -ForegroundColor Green
            
            # Lấy IP
            $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { 
                $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*" 
            } | Select-Object -First 1).IPAddress
            
            Write-Host ""
            Write-Host "Connect from remote machine:" -ForegroundColor Yellow
            Write-Host "  MQTT_HOST=$ip" -ForegroundColor Cyan
            Write-Host "  MQTT_PORT=1883" -ForegroundColor Cyan
        } else {
            Write-Host ""
            Write-Host "⚠ Broker only listening on localhost!" -ForegroundColor Yellow
            Write-Host "Check mosquitto.conf for 'listener 1883 0.0.0.0'" -ForegroundColor Yellow
        }
    } else {
        Write-Host "❌ Broker not listening on port 1883" -ForegroundColor Red
    }
} else {
    Write-Host "❌ Mosquitto not found at: $mosquittoPath" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
