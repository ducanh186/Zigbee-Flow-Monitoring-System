# WFMS Gateway - Quick Start Script for UI Developers
# Double-click to run fake gateway (no hardware needed)

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  WFMS Gateway - Fake UART Mode" -ForegroundColor Cyan
Write-Host "  For UI Development (No Hardware Needed)" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path "gateway\service.py")) {
    Write-Host "ERROR: Must run from wfms/ directory!" -ForegroundColor Red
    Write-Host "Current location: $PWD" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Fix: Right-click this file > 'Run with PowerShell' from wfms/ folder" -ForegroundColor Yellow
    Write-Host ""
    Pause
    exit 1
}

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found!" -ForegroundColor Red
    Write-Host "  Install Python 3.11+ from https://python.org" -ForegroundColor Yellow
    Pause
    exit 1
}

# Check dependencies
Write-Host ""
Write-Host "Checking dependencies..." -ForegroundColor Yellow

$missingDeps = $false
try {
    python -c "import paho.mqtt" 2>&1 | Out-Null
} catch {
    $missingDeps = $true
}

if ($missingDeps) {
    Write-Host "✗ Missing dependencies" -ForegroundColor Red
    Write-Host "  Installing..." -ForegroundColor Yellow
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
        Pause
        exit 1
    }
} else {
    Write-Host "✓ Dependencies OK" -ForegroundColor Green
}

# Check Mosquitto
Write-Host ""
Write-Host "Checking MQTT broker..." -ForegroundColor Yellow
try {
    $mosquittoService = Get-Service -Name mosquitto -ErrorAction Stop
    if ($mosquittoService.Status -ne "Running") {
        Write-Host "✗ Mosquitto service not running" -ForegroundColor Red
        Write-Host "  Starting Mosquitto..." -ForegroundColor Yellow
        Start-Service mosquitto
        Start-Sleep -Seconds 2
    }
    Write-Host "✓ Mosquitto running" -ForegroundColor Green
} catch {
    Write-Host "✗ Mosquitto not installed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Install Mosquitto MQTT broker:" -ForegroundColor Yellow
    Write-Host "  winget install EclipseFoundation.Mosquitto" -ForegroundColor Cyan
    Write-Host "Or download from: https://mosquitto.org/download/" -ForegroundColor Cyan
    Write-Host ""
    Pause
    exit 1
}

# Start gateway
Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  Starting Gateway in FAKE UART mode..." -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Gateway will:" -ForegroundColor Yellow
Write-Host "  • Publish telemetry every 1 second" -ForegroundColor White
Write-Host "  • Listen for valve commands on MQTT" -ForegroundColor White
Write-Host "  • Respond to ON/OFF commands with ACK" -ForegroundColor White
Write-Host ""
Write-Host "MQTT Topics:" -ForegroundColor Yellow
Write-Host "  Subscribe: wfms/lab1/state (valve status, flow, battery)" -ForegroundColor White
Write-Host "  Subscribe: wfms/lab1/ack (command acknowledgments)" -ForegroundColor White
Write-Host "  Publish:   wfms/lab1/cmd/valve (ON/OFF commands)" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Green
Write-Host ""

# Run gateway
python -m gateway.service --fake-uart

# Cleanup on exit
Write-Host ""
Write-Host "Gateway stopped." -ForegroundColor Yellow
Pause
