# Setup Firewall for Streamlit Dashboard
# Run this script as Administrator

Write-Host "Setting up firewall rule for Streamlit port 8502..." -ForegroundColor Cyan

# Remove existing rule if it exists
netsh advfirewall firewall delete rule name="Streamlit 8502" 2>$null

# Add new firewall rule
$result = netsh advfirewall firewall add rule name="Streamlit 8502" dir=in action=allow protocol=TCP localport=8502

if ($LASTEXITCODE -eq 0) {
    Write-Host "Firewall rule added successfully!" -ForegroundColor Green
    Write-Host ""
    
    # Get local IP address
    $ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*"} | Select-Object -ExpandProperty IPAddress
    
    if ($ips) {
        Write-Host "Your PC IP addresses:" -ForegroundColor Yellow
        foreach ($ip in $ips) {
            Write-Host "  http://${ip}:8502" -ForegroundColor Green
        }
    }
    
    Write-Host ""
    Write-Host "Testing if port 8502 is listening..." -ForegroundColor Cyan
    $listening = netstat -ano | findstr ":8502"
    if ($listening) {
        Write-Host "Port 8502 is active:" -ForegroundColor Green
        Write-Host $listening
    } else {
        Write-Host "Port 8502 not yet active - run Dashboard first" -ForegroundColor Yellow
    }
}
else {
    Write-Host "Failed to add firewall rule" -ForegroundColor Red
    Write-Host "Please run this script as Administrator" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
