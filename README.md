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
├── Coordinator_Node/           # Zigbee coordinator firmware (C)
│   ├── app/                   # Application logic
│   │   ├── app.c             # Main application
│   │   ├── uart_link.c       # UART communication
│   │   ├── net_mgr.c         # Network management
│   │   ├── valve_ctrl.c      # Valve control logic
│   │   ├── telemetry_rx.c    # Telemetry receiver
│   │   ├── cmd_handler.c     # Command handler
│   │   └── lcd_ui.c          # LCD display interface
│   ├── main.c                # Entry point
│   └── INSTALLED_COMPONENTS.md
├── Sensor_Node/               # Flow sensor firmware (C)
│   ├── app.c                 # Sensor application
│   ├── main.c                # Entry point
│   └── README.md
├── Vavle_Node/               # Valve actuator firmware (C)
│   ├── app.c                 # Valve application
│   ├── main.c                # Entry point
│   └── README.md
├── Dashboard_Coordinator/     # PC Dashboard (Python)
│   ├── dashboard.py          # Streamlit UI
│   ├── pc_gateway.py         # Serial gateway service
│   ├── preview.html          # UI preview
│   ├── requirements.txt      # Python dependencies
│   └── README.md
├── Gate_Way_Z3/              # MQTT Gateway integration
│   └── gateway_mqtt.py       # MQTT bridge
├── file_project/             # Simplicity Studio project files
│   ├── Coordinator_Node.sls
│   ├── Sensor node.sls
│   └── Valve_node.sls
├── doc/                      # Documentation
│   └── CLI_COMMANDS_REFERENCE.md
├── run_dashboard.bat         # Quick start script
├── setup_firewall.ps1        # Firewall configuration
└── README.md                 # This file
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

### 2. Install Dashboard Dependencies

```bash
cd Dashboard_Coordinator
pip install -r requirements.txt
```

### 3. Run Dashboard

**Windows:**
```bash
run_dashboard.bat
```

**Manual:**
```bash
cd Dashboard_Coordinator
streamlit run dashboard.py
```

- Browser opens automatically
- Select COM port in sidebar
- Click "Connect"
- Dashboard updates in real-time

## 📡 Communication Protocol

The system uses a text-based protocol over UART (115200 baud):

### Coordinator → PC (Telemetry Data)
```
@DATA {"v":1,"flow":120,"battery":90,"valve":"open"}
```

### PC → Coordinator (Commands)
```
@CMD {"id":1,"op":"valve_set","value":"open"}
@CMD {"id":2,"op":"threshold_set","close_th":80,"open_th":20}
```

### Coordinator → PC (Acknowledgments)
```
@ACK {"id":1,"ok":true,"msg":"valve opened","valve":"open"}
```

## 🎨 Dashboard Features

### 1. Real-time Metric Cards
- **Flow Monitor**: Dynamic color-coded display with status indicators (HIGH/NORMAL/LOW)
- **Battery Status**: Progress bar with percentage and low-battery warnings
- **Valve Control**: Real-time valve status with OPEN/CLOSE toggle buttons

### 2. Data Visualization
- **Live Chart (5 min)**: Real-time flow and battery readings with threshold lines
- **Hourly Analytics**: Average/Max/Min flow values for the last 24 hours
- **Daily Summary**: Bar chart showing average flow per day over 30 days
- **Historical Data**: SQLite database with full telemetry history

### 3. Control Interface
- **Connection Manager**: COM port selection and connection status
- **Threshold Configuration**: Set automatic valve control thresholds (close_th, open_th)
- **Manual Valve Override**: Direct valve control bypassing auto mode
- **Auto Refresh**: Configurable update interval (1-10 seconds)

## ⚙️ System Architecture

```
┌─────────────┐     Zigbee      ┌─────────────┐
│ Sensor Node │───────────────▶│  Coordinator│
│ (Flow+Batt) │                 │    Node     │
└─────────────┘                 └──────┬──────┘
                                       │ UART
┌─────────────┐     Zigbee             │
│ Valve Node  │◀───────────────────┬──┘
│ (Actuator)  │                     │
└─────────────┘                     │
                            ┌──────▼──────┐
                            │ PC Gateway  │
                            │  (Serial)   │
                            └──────┬──────┘
                                   │
                            ┌──────▼──────┐
                            │  Dashboard  │
                            │  (Streamlit)│
                            └─────────────┘
```

### Data Flow
1. **Sensor → Coordinator**: Flow and battery telemetry via Zigbee
2. **Coordinator → PC**: Aggregated data via UART (@DATA messages)
3. **PC → Coordinator**: Commands via UART (@CMD messages)
4. **Coordinator → Valve**: Control commands via Zigbee
5. **All Nodes → PC**: Acknowledgments and status updates

## 🔧 Firmware Components

### Coordinator Node
- **Network Manager** (`net_mgr.c`): Zigbee network setup and device management
- **UART Link** (`uart_link.c`): Serial communication with PC
- **Command Handler** (`cmd_handler.c`): Process PC commands
- **Telemetry Receiver** (`telemetry_rx.c`): Collect sensor data
- **Valve Controller** (`valve_ctrl.c`): Automatic valve control logic
- **LCD UI** (`lcd_ui.c`): Local display interface
- **CLI Commands** (`cli_commands.c`): Debug console interface

### Sensor Node
- Flow sensor reading and calibration
- Battery voltage monitoring
- Periodic Zigbee transmission
- Low-power sleep modes

### Valve Node
- Stepper motor or solenoid valve control
- Remote command processing
- Status reporting
- Fail-safe mechanisms

# 1. Start Mosquitto broker (if not running)
```bash
# 1. Start Mosquitto broker (if not running)
net start mosquitto

# Or:
"C:\Program Files\mosquitto\mosquitto.exe" -v
```

# 2. Start gateway (owns COM13)

```bash
.\run_gateway.bat
```
# 3. Start dashboard (one or more instances)


```bash
.\run_dashboard_mqtt.bat
```
## 🧪 Development & Testing

### Gateway Testing

```python
from Dashboard_Coordinator.pc_gateway import ZigbeeGateway

gateway = ZigbeeGateway()

# Get recent telemetry
rows = gateway.get_telemetry_last_n(100)
print(f"Last 100 records: {len(rows)}")

# Get hourly aggregates
hourly = gateway.get_aggregated_data('hour', limit=24)
print(f"Hourly data: {len(hourly)} hours")
```

## 🔗 Integration & Deployment

### Firmware Integration Checklist

- [ ] Implement protocol format correctly (see protocol documentation)
- [ ] Test serial communication with terminal emulator
- [ ] Verify periodic @DATA transmission
- [ ] Validate JSON format: `"valve":"open"` or `"closed"` (lowercase)
- [ ] Test threshold_set command with NVM persistence
- [ ] Test valve_set command with acknowledgment
- [ ] Verify automatic valve control logic

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
