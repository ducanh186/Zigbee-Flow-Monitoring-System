# Smoke Tests

Quick sanity checks to verify the system is working.

## What are Smoke Tests?

"Smoke tests" are quick, basic tests to check if the system is "alive" and core functionality works.
Think of it like turning on a machine and checking if smoke comes out (bad) or it runs normally (good).

## Available Tests

### MQTT Tests
- `test_mqtt_connection.ps1` - Check if MQTT broker is reachable
- `test_local_mqtt.ps1` - Test MQTT pub/sub locally
- `test_mqtt.ps1` - Full MQTT protocol test

### Gateway Tests  
- `test_admin_api.ps1` - Test Admin API endpoints
- `test_tx.ps1` - Test UART transmission
- `run_fake.ps1` - Run gateway with fake UART for testing

### CLI Tests
- `test_cli.py` - Test CLI command interface

## Usage

Run individual tests:
```powershell
cd tests\smoke
.\test_mqtt_connection.ps1
.\test_admin_api.ps1
python test_cli.py
```

Run with fake UART (no hardware needed):
```powershell
.\run_fake.ps1
```

## When to Run

- After making changes to protocol code
- Before deploying to production
- When debugging connectivity issues
- After system restart to verify everything works
