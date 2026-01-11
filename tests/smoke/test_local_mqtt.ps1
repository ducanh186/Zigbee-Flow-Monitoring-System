# Test MQTT Broker Local - May A
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MQTT Broker Test (Local - May A)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Kiem tra broker co chay khong
Write-Host "[1] Checking broker status..." -ForegroundColor Yellow
$brokerProcess = Get-Process mosquitto -ErrorAction SilentlyContinue
if ($brokerProcess) {
    Write-Host "OK Mosquitto is running (PID: $($brokerProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "X Mosquitto is NOT running!" -ForegroundColor Red
    Write-Host "Start broker first with: mosquitto -c mosquitto.conf -v" -ForegroundColor Yellow
    exit 1
}

# 2. Kiem tra port
Write-Host ""
Write-Host "[2] Checking port 1883..." -ForegroundColor Yellow
$portCheck = netstat -ano | findstr ":1883.*LISTENING"
if ($portCheck -match "0\.0\.0\.0:1883") {
    Write-Host "OK Listening on all interfaces (0.0.0.0:1883)" -ForegroundColor Green
    Write-Host "  $portCheck" -ForegroundColor Cyan
} elseif ($portCheck -match "127\.0\.0\.1:1883") {
    Write-Host "! Only listening on localhost!" -ForegroundColor Yellow
    Write-Host "  Restart broker with: mosquitto -c mosquitto.conf -v" -ForegroundColor Yellow
} else {
    Write-Host "X Port 1883 is not listening" -ForegroundColor Red
    exit 1
}

# 3. Lay IP
Write-Host ""
Write-Host "[3] Network information..." -ForegroundColor Yellow
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { 
    $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*" 
} | Select-Object -First 1).IPAddress
Write-Host "  Local IP: $ip" -ForegroundColor Cyan
Write-Host "  MQTT URL: mqtt://$ip:1883" -ForegroundColor Cyan

# 4. Test publish/subscribe
Write-Host ""
Write-Host "[4] Testing MQTT pub/sub..." -ForegroundColor Yellow
Write-Host "  Starting subscriber in background..." -ForegroundColor Gray

# Add mosquitto to PATH
$env:PATH += ";C:\Program Files\mosquitto"

# Start subscriber job
$subJob = Start-Job -ScriptBlock {
    param($brokerIP)
    $env:PATH += ";C:\Program Files\mosquitto"
    & mosquitto_sub -h $brokerIP -t "test/#" -v -C 1
} -ArgumentList $ip

Start-Sleep -Seconds 1

# Publish test message
Write-Host "  Publishing test message..." -ForegroundColor Gray
try {
    & mosquitto_pub -h $ip -t "test/hello" -m "Hello from May A - $(Get-Date -Format 'HH:mm:ss')"
    
    # Wait for result
    $result = Wait-Job $subJob -Timeout 5 | Receive-Job
    Remove-Job $subJob -Force

    if ($result) {
        Write-Host "OK Pub/Sub test PASSED!" -ForegroundColor Green
        Write-Host "  Received: $result" -ForegroundColor Cyan
    } else {
        Write-Host "X Pub/Sub test FAILED (timeout)" -ForegroundColor Red
        Write-Host "  Check broker logs for errors" -ForegroundColor Yellow
    }
} catch {
    Write-Host "X mosquitto_pub/sub not found!" -ForegroundColor Red
    Write-Host "  Error: $_" -ForegroundColor Yellow
    Remove-Job $subJob -Force -ErrorAction SilentlyContinue
}

# 5. Firewall check
Write-Host ""
Write-Host "[5] Checking firewall rule..." -ForegroundColor Yellow
$fwRule = Get-NetFirewallRule -DisplayName "Mosquitto MQTT Broker (TCP 1883)" -ErrorAction SilentlyContinue
if ($fwRule) {
    if ($fwRule.Enabled -eq 'True') {
        Write-Host "OK Firewall rule exists and is enabled" -ForegroundColor Green
    } else {
        Write-Host "! Firewall rule exists but is DISABLED" -ForegroundColor Yellow
    }
} else {
    Write-Host "! Firewall rule NOT found" -ForegroundColor Yellow
    Write-Host "  Run setup_mosquitto_lan.ps1 as Administrator to add firewall rule" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Broker Status: " -NoNewline
if ($brokerProcess -and ($portCheck -match "0\.0\.0\.0")) {
    Write-Host "READY OK" -ForegroundColor Green
} else {
    Write-Host "NOT READY X" -ForegroundColor Red
}
Write-Host ""
Write-Host "Next steps for remote testing (May B):" -ForegroundColor Yellow
Write-Host "1. Copy test_mqtt_connection.ps1 to May B" -ForegroundColor White
Write-Host "2. Run: .\test_mqtt_connection.ps1 -BrokerIP $ip" -ForegroundColor Cyan
Write-Host "3. Or test manually:" -ForegroundColor White
Write-Host "   mosquitto_sub -h $ip -t 'test/#' -v" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
