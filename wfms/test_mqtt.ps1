# WFMS - Quick MQTT Test Commands
# Helper script for UI developers to test valve control

param(
    [Parameter(Position=0)]
    [ValidateSet("on", "off", "sub", "help")]
    [string]$Action = "help"
)

$MQTT_HOST = "127.0.0.1"
$MQTT_PORT = 1883
$TOPIC_CMD = "wfms/lab1/cmd/valve"
$TOPIC_ALL = "wfms/lab1/#"

function Show-Help {
    Write-Host ""
    Write-Host "WFMS Quick Test Commands" -ForegroundColor Cyan
    Write-Host "========================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\test_mqtt.ps1 on      # Turn valve ON" -ForegroundColor White
    Write-Host "  .\test_mqtt.ps1 off     # Turn valve OFF" -ForegroundColor White
    Write-Host "  .\test_mqtt.ps1 sub     # Subscribe to all topics (view data)" -ForegroundColor White
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  # Terminal 1: Subscribe to see all data" -ForegroundColor Gray
    Write-Host "  .\test_mqtt.ps1 sub" -ForegroundColor White
    Write-Host ""
    Write-Host "  # Terminal 2: Send ON command" -ForegroundColor Gray
    Write-Host "  .\test_mqtt.ps1 on" -ForegroundColor White
    Write-Host ""
    Write-Host "  # Terminal 2: Send OFF command" -ForegroundColor Gray
    Write-Host "  .\test_mqtt.ps1 off" -ForegroundColor White
    Write-Host ""
}

function Get-MosquittoPath {
    $paths = @(
        "C:\Program Files\mosquitto\mosquitto_pub.exe",
        "C:\Program Files\mosquitto\mosquitto_sub.exe",
        "$env:ProgramFiles\mosquitto\mosquitto_pub.exe"
    )
    
    foreach ($path in $paths) {
        if (Test-Path $path) {
            return Split-Path $path
        }
    }
    
    # Try to find in PATH
    $pub = Get-Command mosquitto_pub -ErrorAction SilentlyContinue
    if ($pub) {
        return Split-Path $pub.Source
    }
    
    return $null
}

$mosquittoPath = Get-MosquittoPath

if (-not $mosquittoPath) {
    Write-Host "ERROR: Mosquitto not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Install Mosquitto:" -ForegroundColor Yellow
    Write-Host "  winget install EclipseFoundation.Mosquitto" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

$mosquittoPub = Join-Path $mosquittoPath "mosquitto_pub.exe"
$mosquittoSub = Join-Path $mosquittoPath "mosquitto_sub.exe"

switch ($Action) {
    "on" {
        $cid = "ui_on_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        $timestamp = [int][double]::Parse((Get-Date -UFormat %s))
        $payload = @{
            cid = $cid
            value = "ON"
            by = "test_script"
            ts = $timestamp
        } | ConvertTo-Json -Compress
        
        Write-Host ""
        Write-Host "Sending ON command..." -ForegroundColor Yellow
        Write-Host "  CID: $cid" -ForegroundColor Gray
        Write-Host "  Payload: $payload" -ForegroundColor Gray
        Write-Host ""
        
        echo $payload | & $mosquittoPub -h $MQTT_HOST -p $MQTT_PORT -t $TOPIC_CMD -l
        
        Write-Host "✓ Command sent!" -ForegroundColor Green
        Write-Host "  Check subscriber to see ACK" -ForegroundColor Gray
        Write-Host ""
    }
    
    "off" {
        $cid = "ui_off_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        $timestamp = [int][double]::Parse((Get-Date -UFormat %s))
        $payload = @{
            cid = $cid
            value = "OFF"
            by = "test_script"
            ts = $timestamp
        } | ConvertTo-Json -Compress
        
        Write-Host ""
        Write-Host "Sending OFF command..." -ForegroundColor Yellow
        Write-Host "  CID: $cid" -ForegroundColor Gray
        Write-Host "  Payload: $payload" -ForegroundColor Gray
        Write-Host ""
        
        echo $payload | & $mosquittoPub -h $MQTT_HOST -p $MQTT_PORT -t $TOPIC_CMD -l
        
        Write-Host "✓ Command sent!" -ForegroundColor Green
        Write-Host "  Check subscriber to see ACK" -ForegroundColor Gray
        Write-Host ""
    }
    
    "sub" {
        Write-Host ""
        Write-Host "Subscribing to all WFMS topics..." -ForegroundColor Yellow
        Write-Host "  Host: $MQTT_HOST" -ForegroundColor Gray
        Write-Host "  Topics: $TOPIC_ALL" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Press Ctrl+C to stop" -ForegroundColor Green
        Write-Host ""
        
        & $mosquittoSub -h $MQTT_HOST -p $MQTT_PORT -t $TOPIC_ALL -v
    }
    
    "help" {
        Show-Help
    }
}
