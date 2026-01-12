# Mosquitto Broker Scripts

Quick management scripts for the MQTT broker.

## Scripts

### 1. `start_broker.ps1` - Start Broker
Starts Mosquitto broker with LAN configuration.

**What it does:**
- Verifies `mosquitto.conf` exists
- Gets local IP address
- Starts broker with verbose logging
- Shows listening address and LAN URL

**Usage:**
```powershell
.\start_broker.ps1
```

**Output:**
```
Listening on: 0.0.0.0:1883
LAN Address: mqtt://192.168.1.100:1883
Press Ctrl+C to stop
```

**Ctrl+C to stop broker and close window.**

---

### 2. `restart_broker.ps1` - Restart Broker
Stops any running Mosquitto process and starts fresh.

**What it does:**
- Kills existing mosquitto processes
- Waits 2 seconds
- Starts fresh broker
- Verifies listening on port 1883
- Shows connection info

**Usage:**
```powershell
# Run as Administrator (recommended to kill existing process)
.\restart_broker.ps1
```

**When to use:**
- After making changes to `mosquitto.conf`
- If broker becomes unresponsive
- To reset all client connections

---

## Quick Start

### Development (local only):
```powershell
cd tools\mqtt
.\start_broker.ps1
```
Then in another terminal:
```powershell
cd wfms
python -m gateway.service
```

### LAN (remote machines can connect):
```powershell
# First time: setup firewall + persistence
cd ..\setup
.\setup_mosquitto_lan.ps1

# Then start broker
cd ..\mqtt
.\start_broker.ps1
```

### After configuration changes:
```powershell
.\restart_broker.ps1
```

---

## Monitoring Broker

### Check if broker is running:
```powershell
netstat -ano | findstr ":1883"
```

### View connections:
```powershell
Get-Process mosquitto | Format-List
```

### Stop broker manually:
```powershell
Stop-Process -Name mosquitto -Force
```

---

## Related Files

- **Config:** `mosquitto.conf` (at root)
- **Data:** `mosquitto_data/` (at root)
- **Setup:** See `tools/setup/README.md`

