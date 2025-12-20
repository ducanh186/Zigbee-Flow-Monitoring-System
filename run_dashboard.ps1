# Zigbee Flow Monitoring Dashboard Runner
# PowerShell script to run the Streamlit dashboard

Write-Host "Starting Zigbee Flow Monitoring Dashboard..." -ForegroundColor Green
Write-Host ""

# Change to script directory
Set-Location $PSScriptRoot

# Kill existing processes that might be using COM7
Write-Host "Closing existing Streamlit/Python processes that may be using COM7..." -ForegroundColor Yellow

# Kill streamlit processes
Get-Process -Name streamlit -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Kill python processes running dashboard or gateway
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like '*dashboard*' -or $_.CommandLine -like '*gateway*' -or $_.CommandLine -like '*streamlit*'
} | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "Waiting for COM ports to be released..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
Write-Host ""

# Check if streamlit is installed
try {
    $null = Get-Command streamlit -ErrorAction Stop
    Write-Host "Streamlit found, launching dashboard..." -ForegroundColor Cyan
    Write-Host ""
    
    # Run streamlit
    streamlit run dashboard.py
}
catch {
    Write-Host "Error: Streamlit is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Install it with: pip install streamlit" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}
