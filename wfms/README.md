# WFMS — Water Flow Monitoring System (Gateway Service)

## Architecture Overview

For the full end-to-end system architecture (Coordinator, Sensor/Valve Nodes, Gateway, MQTT, Dashboards), see the root project README at `../README.md`.

This document focuses specifically on the **WFMS gateway service**: the UART↔MQTT bridge, local Admin API, and gateway-side configuration.

---

## 🚀 Quick Start

### System Requirements
- **Python 3.11+**
- **Windows / Linux / macOS**
- **MQTT Broker** (Mosquitto, EMQX, or equivalent)
- **Zigbee Coordinator** connected via USB serial port

### 1. Create Virtual Environment

**Windows:**
```powershell
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies:**
- `paho-mqtt==1.6.1` — MQTT client (pinned to avoid v2.x breaking changes)
- `pyserial` — Serial UART communication
- `fastapi` + `uvicorn` — Local HTTP Admin API
- `python-dotenv` — Environment variable loader
- `pydantic` — Config validation & type checking

### 3. Configure Environment

Copy `.env.example` to `.env` and customize:

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

**Key settings in `.env`:**

| Variable | Example | Purpose |
|----------|---------|---------|
| `UART_PORT` | `COM11` | Serial port (Windows: `COM*`, Linux: `/dev/ttyUSB*`) |
| `UART_BAUD` | `115200` | Serial baud rate |
| `MQTT_HOST` | `127.0.0.1` | MQTT broker address |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USER` | `wfms_user` | MQTT auth (leave empty if no auth) |
| `MQTT_PASS` | `changeme` | MQTT password |
| `SITE` | `lab1` | Site ID for MQTT topics: `wfms/{SITE}/...` |
| `RULE_LOCK` | `0` | Lock mode (1 = reject all valve commands) |
| `ACK_TIMEOUT_S` | `3` | Command ACK timeout (seconds) |
| `API_PORT` | `8080` | Local Admin API port |

### 4. Start Gateway Service

**Fake UART mode** (simulate sensor data, no hardware needed):
```bash
python -m gateway.service --fake-uart
```

**Real UART mode** (with Zigbee Coordinator connected):
```bash
python -m gateway.service
```

**Override UART settings:**
```bash
python -m gateway.service --uart COM10 --baud 115200
```

**Debug mode** (verbose logging):
```bash
python -m gateway.service --fake-uart --debug
```

---

## Project Structure

```
wfms/
├── gateway/
│   ├── service.py          Main event loop (UART reader + MQTT router)
│   ├── uart.py             Serial parsing & frame extraction
│   ├── config.py           Environment config loader (Pydantic)
│   ├── rules.py            Business rules (lock, cooldown, dedup)
│   ├── runtime.py          Runtime statistics & state
│   └── admin_api.py        Local HTTP API (localhost:8080)
│
├── common/
│   ├── contract.py         MQTT topics, operations & constants ⭐
│   └── proto.py            Protocol parser/builder (@DATA, @ACK, @CMD, @LOG)
│
├── dashboards/             (Future: Streamlit/Vue apps)
│
├── mosquitto.conf          MQTT broker config (reference only)
├── requirements.txt        Python dependencies
├── .env.example            Configuration template
└── README.md               This file
```

---

## Protocol Overview

For a high-level description of the UART frame format and MQTT topic structure, refer to the **Communication Protocol** section in the root project README.

This gateway implements that contract in:
- common/proto.py — frame parsing/building and operation mapping
- common/contract.py — MQTT topics, site prefix, and constants

---

## Configuration & Constants

### Key Files

| File | Purpose | Edit When |
|------|---------|-----------|
| [contract.py](common/contract.py) | MQTT topics, operation enums | Adding new operation types or topics |
| [proto.py](common/proto.py) | Protocol parser & builder | Changing frame format or translations |
| [service.py](gateway/service.py) | Main event loop | Adding MQTT handlers or routing logic |
| [config.py](gateway/config.py) | Environment config loader | Adding new configuration parameters |

### Environment Variables (See `.env.example`)

**UART Settings:**
- `UART_PORT` — Serial port name
- `UART_BAUD` — Baud rate (default: 115200)

**MQTT Settings:**
- `MQTT_HOST`, `MQTT_PORT` — Broker endpoint
- `MQTT_USER`, `MQTT_PASS` — Auth credentials (optional)
- `SITE` — Site identifier for topics

**Business Rules:**
- `RULE_LOCK` — Lock all commands (0=off, 1=on)
- `RULE_COOLDOWN_USER_S` — Per-user command cooldown
- `RULE_COOLDOWN_GLOBAL_S` — Global command cooldown
- `RULE_DEDUPE_TTL_S` — Duplicate command deduplication window
- `ACK_TIMEOUT_S` — Wait time for command ACK

**Admin API:**
- `API_HOST` — API listen address (default: 127.0.0.1)
- `API_PORT` — API listen port (default: 8080)
- `API_TOKEN` — Token for POST/DELETE endpoints (leave empty to disable)

---

## Common Operations

### Test MQTT Connection (No Hardware)
```bash
cd ../tests/smoke
./test_mqtt_connection.ps1
```

### Monitor MQTT Traffic (Real-time)
```bash
cd ../tools/mqtt
python mqtt_monitor.py
```

### Publish Test Message
```powershell
mosquitto_pub -h localhost -t wfms/lab1/cmd/valve -m '{"value":"ON"}'
mosquitto_sub -h localhost -t "wfms/lab1/#" -v
```

### Start MQTT Broker
```powershell
cd ../tools/mqtt
./start_broker.ps1
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "Connection refused" on MQTT | Broker not running | Run `cd ../tools/mqtt && ./start_broker.ps1` |
| Gateway won't start | `.env` missing or wrong port | Verify `.env` has `MQTT_HOST`, `UART_PORT` |
| ACK timeouts frequently | UART frame corruption | Increase `ACK_TIMEOUT_S` in `.env` |
| UART parse errors | Line buffering issue | Check `extract_frames()` in `uart.py` |
| Firewall blocks MQTT | Firewall rule missing | Run setup: `cd ../tools/setup && ./setup_mosquitto_lan.ps1` |

---

## For Dashboard/UI Developers

If you're building a dashboard or external client:

1. **Do NOT** connect directly to UART — use MQTT only
2. **Subscribe** to MQTT topics: `wfms/{SITE}/state`, `wfms/lab1/telemetry`, `wfms/lab1/ack`
3. **Publish** commands to: `wfms/{SITE}/cmd/valve` with payload `{"value":"ON"}` or `{"value":"OFF"}`
4. **For admin operations**: Call HTTP API at `http://localhost:8080/` (see [gateway/admin_api.py](gateway/admin_api.py))

### Example (Python + paho-mqtt):
```python
import paho.mqtt.client as mqtt

client = mqtt.Client()
client.connect("127.0.0.1", 1883, 60)

# Subscribe to state updates
client.subscribe("wfms/lab1/state")

# Send valve command
client.publish("wfms/lab1/cmd/valve", '{"value":"ON"}')

# Callback for incoming messages
def on_message(client, userdata, msg):
    print(f"{msg.topic}: {msg.payload.decode()}")

client.on_message = on_message
client.loop_forever()
```

---

## Important Rules

### ⚠️ Sacred Invariants

1. **Only one process connects to UART** — the Gateway Service
2. **Protocol is immutable** — Frame format: `@PREFIX {JSON}\r\n` with **CRLF** line ending
3. **MQTT topics are stable** — Only ADD constants to `contract.py`, never remove or rename
4. **Command IDs auto-increment** — Every command gets a numeric ID; ACK must echo it
5. **ACK timeout is enforced** — Commands without ACK within timeout are logged as errors

### When Modifying Code

- **Adding new operation** → Update `Operation` enum in `proto.py`
- **Adding new MQTT topic** → Add constant to `contract.py` + update `update_site()` function
- **Changing UART format** → Update both `extract_frames()` and `parse_uart_line()`
- **New config parameter** → Add to `config.py` with Pydantic validation + `.env.example`

---

## References

- [../Coordinator_Node/](../Coordinator_Node/) — Zigbee firmware (C)
- [../tools/mqtt/](../tools/mqtt/) — MQTT broker management scripts
- [../tests/smoke/](../tests/smoke/) — Sanity tests & smoke tests

---

## License & Status

- **Status**: Active development (v0.1+)
- **Last Updated**: January 2026
