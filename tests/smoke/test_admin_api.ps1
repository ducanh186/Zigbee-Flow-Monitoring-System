# Test Admin API endpoints
# Run while gateway service is running: python -m gateway.service --fake-uart

$baseUrl = "http://127.0.0.1:8080"

Write-Host "`n=== Testing Admin API ===" -ForegroundColor Cyan

# Test 1: GET /health
Write-Host "`n[1] GET /health" -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$baseUrl/health"
    Write-Host "  up: $($health.up)" -ForegroundColor Green
    Write-Host "  uptime_s: $($health.uptime_s)"
    Write-Host "  mqtt_connected: $($health.mqtt_connected)"
    Write-Host "  uart_connected: $($health.uart_connected)"
    Write-Host "  counters: $($health.counters | ConvertTo-Json -Compress)"
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
}

# Test 2: GET /rules
Write-Host "`n[2] GET /rules" -ForegroundColor Yellow
try {
    $rules = Invoke-RestMethod -Uri "$baseUrl/rules"
    Write-Host "  lock: $($rules.lock)"
    Write-Host "  cooldown_user_s: $($rules.cooldown_user_s)"
    Write-Host "  cooldown_global_s: $($rules.cooldown_global_s)"
    Write-Host "  dedupe_ttl_s: $($rules.dedupe_ttl_s)"
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
}

# Test 3: GET /config
Write-Host "`n[3] GET /config" -ForegroundColor Yellow
try {
    $config = Invoke-RestMethod -Uri "$baseUrl/config"
    Write-Host "  site: $($config.site)"
    Write-Host "  uart_port: $($config.uart_port)"
    Write-Host "  mqtt_host: $($config.mqtt_host)"
    Write-Host "  api_auth_enabled: $($config.api_auth_enabled)"
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
}

# Test 4: GET /logs
Write-Host "`n[4] GET /logs" -ForegroundColor Yellow
try {
    $logs = Invoke-RestMethod -Uri "$baseUrl/logs?limit=5"
    Write-Host "  count: $($logs.count)"
    foreach ($log in $logs.logs) {
        Write-Host "  [$($log.level)] $($log.message)"
    }
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
}

# Test 5: POST /rules (enable lock - no auth needed since API_TOKEN is empty)
Write-Host "`n[5] POST /rules (enable lock)" -ForegroundColor Yellow
try {
    $body = @{ lock = $true } | ConvertTo-Json
    $result = Invoke-RestMethod -Uri "$baseUrl/rules" -Method POST -Body $body -ContentType "application/json"
    Write-Host "  lock enabled: $($result.lock)" -ForegroundColor Green
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
}

# Verify lock is enabled
Write-Host "`n[6] Verify lock is enabled" -ForegroundColor Yellow
try {
    $rules = Invoke-RestMethod -Uri "$baseUrl/rules"
    Write-Host "  lock: $($rules.lock)" -ForegroundColor $(if ($rules.lock) { "Green" } else { "Red" })
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
}

# Test 7: POST /rules (disable lock)
Write-Host "`n[7] POST /rules (disable lock)" -ForegroundColor Yellow
try {
    $body = @{ lock = $false } | ConvertTo-Json
    $result = Invoke-RestMethod -Uri "$baseUrl/rules" -Method POST -Body $body -ContentType "application/json"
    Write-Host "  lock disabled: $(-not $result.lock)" -ForegroundColor Green
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
}

# Test 8: GET /docs (OpenAPI docs)
Write-Host "`n[8] Check OpenAPI docs available" -ForegroundColor Yellow
try {
    $docsResponse = Invoke-WebRequest -Uri "$baseUrl/docs" -UseBasicParsing
    if ($docsResponse.StatusCode -eq 200) {
        Write-Host "  /docs available (HTTP 200)" -ForegroundColor Green
    }
} catch {
    Write-Host "  Error: $_" -ForegroundColor Red
}

Write-Host "`n=== Tests Complete ===" -ForegroundColor Cyan
