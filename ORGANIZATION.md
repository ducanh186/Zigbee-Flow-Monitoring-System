# Project Organization Summary

**Date:** 2026-01-11  
**Status:** ✅ Reorganization Complete

---

## 🎯 Cleanup Objectives Achieved

### ✅ Deleted (Safe)
- `__pycache__/` - Python cache
- `.sunlint-cache/` - Lint cache

### ✅ Archived (for reference, not deleted)
**Location:** `archive/`
- `Dashboard_Coordinator/` - Old dashboard (replaced by wfms)
- `Gate_Way_Z3/` - Old gateway (replaced by wfms)
- `mock_gateway.deprecated.py` - Old mock (use `gateway.service --fake-uart`)
- `telemetry.db` - Test data
- `TEST_3_TERMINAL.md` - Dev notes

### ✅ Reorganized (moved to appropriate folders)

#### `tools/setup/` - One-time initialization
- `setup_mosquitto_lan.ps1` - Setup MQTT broker + LAN
- `setup_firewall.ps1` - Setup Streamlit firewall
- 📖 `README.md` - Setup instructions

#### `tools/mqtt/` - Broker management
- `start_broker.ps1` - Start MQTT broker
- `restart_broker.ps1` - Restart MQTT broker
- `mqtt_monitor.py` - MQTT traffic monitor
- 📖 `README.md` - Broker usage guide

#### `tools/serial/` - Serial/UART utilities
- `configure_valve.py` - Configure valve
- `quick_valve_setup.py` - Quick setup
- `set_valve_target.py` - Set target

#### `tests/smoke/` - Quick sanity tests
- `run_fake.ps1` - Run with fake UART
- `test_admin_api.ps1` - Test API
- `test_cli.py` - Test CLI
- `test_mqtt*.ps1` - Test MQTT
- `test_tx.ps1` - Test UART transmission
- 📖 `README.md` - Test guide

### ✅ Kept at Root (Production)
- `mosquitto.conf` - MQTT config
- `mosquitto.conf.md` - Config documentation
- `mosquitto_data/` - MQTT persistent data
- `README.md` - Project readme
- `.gitignore` - Git ignore rules
- `.vscode/` - Editor settings

### ✅ Kept at Root (Firmware)
- `Coordinator_Node/` - Coordinator firmware (C)
- `Sensor_Node/` - Sensor firmware (C)
- `Vavle_Node/` - Valve firmware (C)
- `file_project/` - Silabs projects
- `doc/` - Documentation

### ✅ Production Gateway (Kept at Root)
- `wfms/` - Main gateway system
  - `gateway/` - UART ↔ MQTT service
  - `common/` - Protocol + contract
  - `dashboards/` - Dashboard utilities
  - `.env` + `.env.example` - Configuration
  - `requirements.txt` - Python deps

---

## 📋 Quick Usage Guide

### First-time Setup (Development Machine)
```powershell
cd tools\setup
.\setup_mosquitto_lan.ps1      # Setup broker + firewall
```

### Start Development
```powershell
# Terminal 1: MQTT Broker
cd tools\mqtt
.\start_broker.ps1

# Terminal 2: Gateway Service
cd wfms
python -m gateway.service

# Terminal 3: (Optional) Monitor MQTT traffic
cd tools\mqtt
python mqtt_monitor.py
```

### Run Tests
```powershell
cd tests\smoke
.\test_mqtt_connection.ps1     # Test MQTT
.\test_admin_api.ps1           # Test Admin API
python test_cli.py             # Test CLI
```

### Restart Broker After Config Change
```powershell
cd tools\mqtt
.\restart_broker.ps1
```

---

## 📁 Directory Structure

```
.
├── archive/                    # Old code (for reference only)
│   ├── Dashboard_Coordinator/
│   ├── Gate_Way_Z3/
│   ├── mock_gateway.deprecated.py
│   └── README.md              # Archive documentation
│
├── tools/                      # Development utilities
│   ├── setup/                 # One-time setup scripts
│   │   ├── setup_mosquitto_lan.ps1
│   │   ├── setup_firewall.ps1
│   │   └── README.md
│   ├── mqtt/                  # MQTT broker management
│   │   ├── start_broker.ps1
│   │   ├── restart_broker.ps1
│   │   ├── mqtt_monitor.py
│   │   └── README.md
│   ├── serial/                # UART/Serial utilities
│   │   ├── configure_valve.py
│   │   ├── quick_valve_setup.py
│   │   └── set_valve_target.py
│   └── README.md
│
├── tests/                      # Test suites
│   └── smoke/                 # Quick sanity tests
│       ├── test_mqtt_connection.ps1
│       ├── test_admin_api.ps1
│       ├── test_cli.py
│       ├── run_fake.ps1
│       └── README.md
│
├── wfms/                       # ⭐ Main gateway system
│   ├── gateway/               # UART ↔ MQTT service
│   │   ├── service.py         # Main service
│   │   ├── uart.py            # UART interface (with extract_frames)
│   │   ├── config.py          # Configuration
│   │   ├── rules.py           # Business rules
│   │   ├── runtime.py         # Runtime state
│   │   └── admin_api.py       # Admin API
│   ├── common/                # Shared utilities
│   │   ├── proto.py           # Protocol parser (with UART_EOL CRLF fix)
│   │   └── contract.py        # MQTT contract
│   ├── .env & .env.example    # Configuration
│   └── requirements.txt       # Dependencies
│
├── Coordinator_Node/          # Zigbee Coordinator firmware
├── Sensor_Node/               # Sensor firmware
├── Vavle_Node/                # Valve firmware
├── file_project/              # Silabs projects
│
├── mosquitto.conf             # ⭐ MQTT broker config
├── mosquitto.conf.md          # Configuration documentation
├── mosquitto_data/            # ⭐ MQTT persistent data
│
└── doc/                        # Documentation
```

---

## 🔧 Recent Fixes Applied

### 1. UART Protocol (wfms/common/proto.py)
- ✅ Changed TX line ending from LF (`\n`) to CRLF (`\r\n`)
- ✅ Added `UART_EOL` constant for consistency

### 2. UART Frame Parsing (wfms/gateway/uart.py)
- ✅ Added `extract_frames()` function to parse multiple frames from single line
- ✅ Handles `@ACK/@INFO` mid-line due to echo/buffering

### 3. UART Reader Loop (wfms/gateway/service.py)
- ✅ Updated `_uart_reader_loop()` to use `extract_frames()`
- ✅ Processes multiple protocol frames per UART read

---

## 📝 Notes

### Why Archive instead of Delete?
- System is in active debug phase
- Need to compare old vs new implementations
- Can quickly restore if regression occurs
- After 2-4 weeks of stable operation, can safely delete

### Smoke Tests
- Use before deploying changes
- Use after making protocol modifications
- Useful for regression testing (did we break something?)

### Tools Organization
- Development tools separated from production code
- Easy to find utilities without cluttering root
- Clear README in each folder with usage examples

---

## ✨ Result: Clean, Organized, Production-Ready

Your project is now structured for:
- ✅ Quick onboarding (see `tools/setup/README.md`)
- ✅ Easy maintenance (tools/tests properly organized)
- ✅ Safe debugging (archive kept for reference)
- ✅ CI/CD ready (clean structure, no cache)
- ✅ Team collaboration (clear folder purposes)
