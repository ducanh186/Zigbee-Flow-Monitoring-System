# Test MQTT Connection from Remote Machine
# Chạy script này trên Máy B để test kết nối tới broker trên Máy A

param(
    [Parameter(Mandatory=$false)]
    [string]$BrokerIP = "10.136.205.235",  # IP của Máy A (sửa nếu cần)
    
    [Parameter(Mandatory=$false)]
    [int]$Port = 1883
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MQTT Connection Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Broker: $BrokerIP:$Port" -ForegroundColor Yellow
Write-Host ""

# 1. Test TCP connection
Write-Host "[1] Testing TCP connection..." -ForegroundColor Yellow
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpClient.Connect($BrokerIP, $Port)
    $tcpClient.Close()
    Write-Host "✓ TCP connection successful" -ForegroundColor Green
} catch {
    Write-Host "❌ TCP connection failed!" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "1. Check broker is running on $BrokerIP" -ForegroundColor White
    Write-Host "2. Check firewall allows port $Port" -ForegroundColor White
    Write-Host "3. Check network connectivity: ping $BrokerIP" -ForegroundColor White
    exit 1
}
Write-Host ""

# 2. Test MQTT subscribe
Write-Host "[2] Testing MQTT subscribe (listening for 5 seconds)..." -ForegroundColor Yellow
Write-Host "Subscribing to: wfms/lab1/#" -ForegroundColor Cyan
Write-Host ""

$mosquittoSub = "C:\Program Files\mosquitto\mosquitto_sub.exe"
if (Test-Path $mosquittoSub) {
    # Subscribe với timeout 5 giây
    $job = Start-Job -ScriptBlock {
        param($exe, $host, $port)
        & $exe -h $host -p $port -t "wfms/lab1/#" -v
    } -ArgumentList $mosquittoSub, $BrokerIP, $Port
    
    Start-Sleep -Seconds 5
    Stop-Job $job
    $output = Receive-Job $job
    Remove-Job $job
    
    if ($output) {
        Write-Host "✓ Received messages:" -ForegroundColor Green
        $output | ForEach-Object { Write-Host "  $_" -ForegroundColor Cyan }
    } else {
        Write-Host "⚠ No messages received (this is OK if Gateway is not running)" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠ mosquitto_sub.exe not found, skipping MQTT test" -ForegroundColor Yellow
}
Write-Host ""

# 3. Hướng dẫn
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Connection Test Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To use this broker in your .env file:" -ForegroundColor Yellow
Write-Host "MQTT_HOST=$BrokerIP" -ForegroundColor Cyan
Write-Host "MQTT_PORT=$Port" -ForegroundColor Cyan
Write-Host ""
Write-Host "To subscribe to all topics:" -ForegroundColor Yellow
Write-Host "mosquitto_sub -h $BrokerIP -t 'wfms/lab1/#' -v" -ForegroundColor Cyan
Write-Host ""
Write-Host "To publish a test message:" -ForegroundColor Yellow
Write-Host "mosquitto_pub -h $BrokerIP -t 'test' -m 'Hello from remote!'" -ForegroundColor Cyan
Write-Host ""
