# Bước 5.5 - Cleanup & Handoff to UI Developer

## Changes Made

### ✅ Deprecated old mock_gateway.py
- Renamed `mock_gateway.py` → `mock_gateway.deprecated.py`
- Added deprecation warning to prevent accidental use
- Points users to new `gateway.service --fake-uart`

### ✅ Created README_FOR_UI_DEV.md
Comprehensive guide for UI developers including:
- Quick start (3 steps)
- MQTT topics table (contract)
- Payload format with examples
- Test scenarios (ON/OFF, duplicate CID, cooldown, timeout)
- Python MQTT client examples
- Troubleshooting guide
- Checklist for UI dev

### ✅ Created helper scripts

**run_fake.ps1** - One-click gateway startup
- Checks Python, dependencies, Mosquitto
- Auto-installs missing dependencies
- Auto-starts Mosquitto service
- Runs gateway in fake mode
- Double-click friendly

**test_mqtt.ps1** - Quick MQTT test commands
- `.\test_mqtt.ps1 on` - Send ON command
- `.\test_mqtt.ps1 off` - Send OFF command
- `.\test_mqtt.ps1 sub` - Subscribe to all topics
- Auto-generates unique CID
- Handles Windows PowerShell JSON escaping

### ✅ Updated main README.md
- Added Quick Links section
- Highlighted README_FOR_UI_DEV.md for UI developers
- Updated "Chạy Gateway Service" section with modes
- Added reference to UI dev guide

## File Structure After Cleanup

```
wfms/
├── gateway/
│   ├── mock_gateway.deprecated.py  ⚠️ DEPRECATED
│   ├── service.py                  ✅ NEW main service
│   ├── uart.py
│   ├── rules.py
│   └── config.py
├── common/
│   ├── proto.py
│   └── contract.py
├── dashboards/
│   └── .gitkeep
├── README.md                       ✏️ Updated
├── README_FOR_UI_DEV.md            ⭐ NEW
├── CONTRACT.md
├── run_fake.ps1                    ⭐ NEW
├── test_mqtt.ps1                   ⭐ NEW
├── requirements.txt
├── .env.example
└── .gitignore
```

## For Person B (UI Developer)

**Start here**: [README_FOR_UI_DEV.md](README_FOR_UI_DEV.md)

**Quick start**:
1. Double-click `run_fake.ps1` (or run `python -m gateway.service --fake-uart`)
2. In new terminal: `.\test_mqtt.ps1 sub` (subscribe to see data)
3. In another terminal: `.\test_mqtt.ps1 on` (send ON command)

**What you get**:
- Telemetry every 1 second (flow, battery, valve status)
- ACK for every command
- Simulated valve behavior (flow changes when ON/OFF)
- Rules enforcement (cooldown, dedupe)

**Contract**:
- Topics: `wfms/lab1/{state,telemetry,ack,cmd/valve,status/gateway}`
- Payload format: See CONTRACT.md
- DO NOT BREAK the contract!

## Testing Checklist

- [x] Gateway runs: `python -m gateway.service --fake-uart`
- [x] Telemetry publishes every 1s
- [x] ON command works (valve=ON, flow increases)
- [x] OFF command works (valve=OFF, flow decreases)
- [x] ACK received for valid commands
- [x] Duplicate CID rejected
- [x] Old mock_gateway.py raises deprecation error
- [x] run_fake.ps1 checks dependencies and starts gateway
- [x] test_mqtt.ps1 sends commands correctly

## Next Steps (Future - Bước 6)

- [ ] Local Admin API (FastAPI endpoints)
  - GET /health, /rules, /config, /logs
  - POST /rules, /config
- [ ] Dashboard Admin (web UI for config)
- [ ] Dashboard User (web UI for monitoring)

---

**Bước 5 + 5.5 HOÀN THÀNH** ✅

UI Developer có thể bắt đầu làm việc ngay mà không cần phần cứng!
