# Tools Directory

Utility scripts for development, debugging, and maintenance.

## `mqtt/`

MQTT testing and monitoring tools:
- `mqtt_monitor.py` - Real-time MQTT message monitor (subscribes to all topics)

### Usage
```powershell
cd tools\mqtt
python mqtt_monitor.py
```

## `serial/`

UART/Serial communication utilities:
- `configure_valve.py` - Configure valve parameters via UART
- `quick_valve_setup.py` - Quick valve setup wizard
- `set_valve_target.py` - Set valve target node

### Usage
```powershell
cd tools\serial
python configure_valve.py --port COM13
python quick_valve_setup.py
python set_valve_target.py --node 0x1234
```

## Notes

These are **development tools**, not part of the production system.
They are kept for:
- Manual testing during development
- Debugging issues
- Quick system checks
- Demonstrations
