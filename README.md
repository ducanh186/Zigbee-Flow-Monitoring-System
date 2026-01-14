# Zigbee Flow Monitoring System

A comprehensive IoT system for real-time flow monitoring and automated valve control using Zigbee wireless protocol. The system consists of Zigbee sensor/actuator nodes, coordinator firmware, and a PC-based dashboard for monitoring and control.

## 📋 Overview

This project implements a complete Zigbee-based flow monitoring solution with three main components:
- **Coordinator Node**: Zigbee coordinator firmware for network management and UART gateway
- **Sensor Node**: Flow and battery monitoring with wireless data transmission
- **Valve Node**: Remote-controlled valve actuator for flow regulation
- **Gateway Service**: Serial communication bridge between coordinator and PC
- **Dashboard UI**: Web-based monitoring interface with real-time charts and controls

## 🗂️ Project Structure

```
Zigbee-Flow-Monitoring-System/
├── Coordinator_Node/        # Zigbee coordinator firmware (C, EFR32)
│   ├── app/                 # Application logic (UART, network, valve, CLI, ...)
│   └── main.c               # Entry point
├── Sensor_Node/             # Flow sensor firmware (C)
├── Vavle_Node/              # Valve actuator firmware (C)
├── wfms/                    # MQTT gateway + dashboards (Python)
│   ├── common/              # Protocol & MQTT contract
│   ├── gateway/             # UART↔MQTT service + Admin API
│   └── dashboards/          # Admin/User web dashboards (Streamlit)
├── tools/                   # PC utilities (MQTT, serial, setup scripts)
├── docs/                    # Project documentation (CLI, conventions, MQTT)
├── file_project/            # Simplicity Studio .sls projects
├── mosquitto_data/          # Mosquitto persistence data (Windows service)
├── archive/                 # Legacy dashboards & experimental code
└── README.md                # This file
```

## 🚀 Quick Start

### Prerequisites
- **Hardware**: Silicon Labs Zigbee development boards (EFR32)
- **Software**: 
  - Simplicity Studio 5 (for firmware development)
  - Python 3.8+ (for dashboard)
  - Git

### 1. Flash Firmware to Nodes

```bash
# Open Simplicity Studio
# Import projects from file_project/
# Build and flash to respective boards:
# - Coordinator_Node.sls → Coordinator board
# - Sensor node.sls → Sensor board
# - Valve_node.sls → Valve board
```

### 2. Install Gateway & Dashboard Dependencies

```bash
cd wfms
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in the `wfms/` directory (copy from `.env.example`):

```bash
cd wfms
copy .env.example .env
# Edit .env and set your COM port and MQTT broker address
```

Key configuration variables:
- `UART_PORT` - Serial port for coordinator (e.g., COM11, /dev/ttyUSB0)
- `MQTT_HOST` - MQTT broker address (localhost for local, or LAN IP for remote access)
- `MQTT_PORT` - MQTT broker port (default: 1883)
- `SITE` - Site identifier for MQTT topics (default: lab1)

### 4. Start the System

The system requires two components running: **MQTT Broker** and **Gateway Service**.

#### Step 1: Start MQTT Broker

**Terminal 1** - Start Mosquitto broker:

```powershell
cd tools\mqtt
.\start_broker.ps1
```

Expected output:
```
mosquitto version 2.0.x starting
Config loaded from mosquitto.conf
Opening ipv4 listen socket on port 1883
mosquitto version 2.0.x running
```

**Keep this terminal running.**

#### Step 2: Start Gateway Service

**Terminal 2** - Start the gateway (UART ↔ MQTT bridge):

```powershell
cd wfms
python -m gateway.service
```

Expected output:
```
[INFO] gateway: WFMS Gateway Service Starting
[INFO] gateway: Site: lab1
[INFO] gateway: MQTT: localhost:1883
[INFO] gateway: UART: COM11 @ 115200
[INFO] gateway.uart: UART connected: COM11 @ 115200
[INFO] gateway: ✓ MQTT connected
[INFO] gateway: ✓ Subscribed to wfms/lab1/cmd/valve
```

**Keep this terminal running.**

#### Step 3: Start Dashboard (Optional)

**Terminal 3** - Start the web dashboard:

```powershell
cd wfms
streamlit run dashboards\admin\admin_dashboard.py --server.address 0.0.0.0 --server.port 8501
```

Access the dashboard at: `http://localhost:8501`

### 5. Verify System Operation

#### Check MQTT Broker
```powershell
# Test MQTT connection
mosquitto_sub -h localhost -t "wfms/lab1/#" -v
```

#### Check Gateway Status
```powershell
# Call Admin API
curl http://127.0.0.1:8080/status
```

#### Monitor Live Data
```powershell
cd tools\mqtt
python mqtt_monitor.py
```

### Testing Without Hardware

Run the gateway in simulation mode:

```powershell
cd wfms
python -m gateway.service --fake-uart
```

This generates synthetic sensor data for testing dashboards and MQTT integration.

## 📡 Communication Protocol

Data between the Coordinator and PC uses a simple text protocol over UART (115200 bps), and the gateway mirrors it to MQTT topics.

- Frame format: `@TYPE {JSON}\r\n` (CRLF line ending)
- `@DATA` – telemetry, `@CMD` – commands, `@ACK` – acknowledgments

Examples:

```text
@DATA {"flow":120,"battery":90,"valve":"open"}
@CMD  {"id":1,"op":"valve_set","value":"open"}
@ACK  {"id":1,"ok":true,"msg":"valve opened"}
```

## 🎨 Dashboard Features

Both the legacy serial dashboard and the new MQTT-based Admin/User dashboards provide:

- Real-time cards for flow, battery level, and valve state
- Live charts plus historical analytics (minutes → days)
- Manual and automatic valve control with configurable thresholds
- Connection status, logs, and basic diagnostics for quick troubleshooting

## ⚙️ System Architecture

High-level data flow:

1. Sensor Node → Coordinator over Zigbee (flow + battery)
2. Coordinator ↔ Gateway PC over UART (`@DATA`, `@CMD`, `@ACK` frames)
3. Gateway service ↔ MQTT broker (`wfms/{SITE}/...` topics)
4. Dashboards and external systems ↔ MQTT + Admin API for monitoring and control

Simplified view:

```text
Sensor / Valve Nodes ⇄ Coordinator ⇄ UART ⇄ Gateway (WFMS) ⇄ MQTT ⇄ Dashboards / Clients
```

### Integration Testing Workflow

1. **Flash Firmware**: Program all nodes with respective firmware
2. **Connect Coordinator**: Connect coordinator to PC via USB
3. **Start Dashboard**: Launch dashboard and select COM port
4. **Verify Telemetry**: Confirm @DATA messages are received and displayed
5. **Test Manual Control**: Click OPEN/CLOSE buttons, verify valve response
6. **Test Auto Mode**: Set thresholds and simulate flow changes
7. **Monitor Performance**: Check response times and battery consumption

## 📝 Technical Notes

### Automatic Valve Control
- **Auto Mode**: Flow ≥ close_th → close valve | Flow ≤ open_th → open valve
- **Manual Override**: Dashboard valve_set command bypasses automatic control
- **State Updates**: Firmware sends @DATA immediately on valve state changes

### Performance Specifications

- **Serial Baudrate**: 115200 bps

### Performance Specifications
- **Serial Baudrate**: 115200 bps
- **Serial Timeout**: 1 second (non-blocking)
- **Database Write**: Per @DATA message (can be batched)
- **UI Refresh Rate**: 1-10 seconds (configurable)
- **Command Timeout**: 2 seconds for ACK response
- **Zigbee Range**: Up to 100m line-of-sight

## 🐛 Troubleshooting

### Dashboard Connection Issues
- **Check COM Port**: Verify correct port selected (use Device Manager on Windows)
- **Verify Firmware**: Ensure coordinator is running and sending @DATA
- **Test Serial**: Use PuTTY/TeraTerm to test raw serial communication
- **Check Drivers**: Install Silicon Labs USB drivers if needed

### No Data Received
- **Baudrate Mismatch**: Verify 115200 baud on both sides
- **Protocol Format**: Ensure @DATA prefix is present
- **JSON Validation**: Test JSON parsing with online validator
- **Buffer Issues**: Check for buffer overflow or incomplete messages

### Command/ACK Timeout
- **Response Time**: Firmware must send ACK within 2 seconds
- **Command Format**: Verify @CMD prefix and JSON structure
- **ID Matching**: Ensure cmd_id in ACK matches sent command
- **Serial Busy**: Check for serial port conflicts

### Zigbee Network Issues
- **Network Formation**: Wait for coordinator to form network (green LED)
- **Device Join**: Ensure sensor/valve nodes join successfully
- **Signal Strength**: Check range and obstacles
- **Channel Interference**: Try different Zigbee channels

## 📚 Documentation

- **CLI Commands Reference**: See `doc/CLI_COMMANDS_REFERENCE.md`
- **Sensor Node Details**: See `Sensor_Node/README.md`
- **Valve Node Details**: See `Vavle_Node/README.md`
- **Dashboard Guide**: See `Dashboard_Coordinator/README.md`
- **Streamlit Docs**: https://docs.streamlit.io/
- **Plotly Charts**: https://plotly.com/python/
- **PySerial**: https://pyserial.readthedocs.io/

## 🛠️ Technology Stack

### Firmware
- **Platform**: Silicon Labs EFR32 (ARM Cortex-M)
- **IDE**: Simplicity Studio 5
- **Protocol**: Zigbee 3.0
- **Language**: C

### PC Software
- **Language**: Python 3.8+
- **Framework**: Streamlit (Dashboard UI)
- **Communication**: PySerial
- **Database**: SQLite3
- **Visualization**: Plotly
- **Optional**: MQTT integration (paho-mqtt)

## 📦 MQTT Gateway (Optional)

The `Gate_Way_Z3/gateway_mqtt.py` provides MQTT integration for IoT cloud platforms:

```bash
cd Gate_Way_Z3
python gateway_mqtt.py
```

Features:

- Publish telemetry to MQTT broker
- Subscribe to command topics
- Bridge between serial and MQTT
- Cloud platform integration (AWS IoT, Azure IoT Hub, etc.)

## 🔐 Security Considerations

- **Zigbee Encryption**: Enable Zigbee network security
- **Serial Access**: Restrict COM port access permissions
- **Database**: Secure SQLite file access
- **MQTT**: Use TLS/SSL for cloud connections
- **Firewall**: Configure firewall rules (see `setup_firewall.ps1`)

## 🚀 Future Enhancements

- [ ] Web-based remote access
- [ ] Multi-coordinator support
- [ ] Historical data export (CSV/Excel)
- [ ] Email/SMS alerts on threshold violations
- [ ] Mobile app integration
- [ ] Machine learning for flow prediction
- [ ] Energy consumption analytics
- [ ] Multi-language support

## 👥 Contributors

This project is developed as part of an IoT flow monitoring system initiative.

- **Firmware Development**: Zigbee coordinator, sensor, and valve firmware
- **Dashboard Development**: Gateway service, UI, and database management
- **Integration**: Protocol design and system testing

## 📄 License

This project is intended for educational and research purposes.

---

**Version**: 2.0  
**Last Updated**: January 5, 2026  
**Status**: Active Development
