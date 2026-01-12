# Mosquitto Configuration

Main configuration file for MQTT Broker.

## Location
**File:** `mosquitto.conf` (at project root)

## Active Configuration

```ini
# Listen on all network interfaces (allows LAN connections)
listener 1883 0.0.0.0
allow_anonymous true

# Logging
log_dest stdout
log_type all

# Persistence (survives broker restart)
persistence true
persistence_location mosquitto_data/

# Autosave interval
autosave_interval 300
```

## What Each Setting Does

| Setting | Value | Purpose |
|---------|-------|---------|
| `listener` | `1883 0.0.0.0` | Listen on all IPs, port 1883 |
| `allow_anonymous` | `true` | Allow connections without credentials |
| `persistence` | `true` | Retain messages across restarts |
| `persistence_location` | `mosquitto_data/` | Where to store persistent data |
| `autosave_interval` | `300` | Save to disk every 300 seconds |

## Usage

### Start Broker
```powershell
cd tools\mqtt
.\start_broker.ps1
```

### Restart After Config Change
```powershell
cd tools\mqtt
.\restart_broker.ps1
```

## Common Configuration Changes

### For Testing Only (No Network):
```ini
listener 1883 127.0.0.1
allow_anonymous true
```
Then restart broker.

### Enable Authentication:
```ini
listener 1883 0.0.0.0
allow_anonymous false
password_file /path/to/passwords.txt
```

### Disable Persistence:
```ini
persistence false
```

### Increase Logging:
```ini
log_dest file /var/log/mosquitto/mosquitto.log
log_type all
```

## Data Location
Persistent data stored in: `mosquitto_data/mosquitto.db`

## Troubleshooting

### Port 1883 already in use:
- See `tools/setup/README.md` for resolution

### Changes not taking effect:
- Run `.\restart_broker.ps1` (not just stop/start)

### Connection refused from remote machine:
- Check firewall rule: `netsh advfirewall firewall show rule name="Mosquitto MQTT Broker"`
- Verify `listener 1883 0.0.0.0` in this file
- Verify `mosquitto_data/` folder exists

## Reference
- Official docs: https://mosquitto.org/documentation/
- Man page: `mosquitto -h` in terminal
