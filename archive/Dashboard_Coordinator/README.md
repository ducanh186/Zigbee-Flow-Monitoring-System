# 📡 Zigbee Flow Monitoring Dashboard

Real-time monitoring and control interface for Zigbee-based water flow system.

## 🚀 Quick Start (Demo)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Dashboard
**Windows:**
```bash
# From project root
.\run_dashboard.bat
```

**Manual:**
```bash
cd Dashboard_Coordinator
streamlit run dashboard.py
```

### 3. Connect to Coordinator
1. Dashboard auto-detects JLink CDC UART port
2. Default baudrate: **115200** (auto-verified)
3. Click **"▶ CONNECT NOW"**
4. ✅ System Online!

---

## 📁 File Structure

```
Dashboard_Coordinator/
├── dashboard.py          ← Main entry point (Streamlit UI)
├── pc_gateway.py         ← Optional standalone gateway CLI
├── scan_COM11.py         ← Diagnostic tool (port/baudrate scanner)
├── requirements.txt      ← Python dependencies
├── DEMO_CHECKLIST.md     ← Complete demo workflow
└── README.md             ← This file
```

---

## 🔧 Files Overview

### `dashboard.py` - Main Dashboard (27.4 KB)
**Primary interface** với tất cả tính năng:
- ✅ Auto-detect COM port & baudrate
- ✅ Real-time telemetry (flow, battery, valve)
- ✅ Valve control (open/close) với @ACK confirmation
- ✅ Network config (PAN ID, channel, TX power)
- ✅ Binding table setup
- ✅ Response inspector (@ACK/@INFO/@LOG)
- ✅ Terminal log viewer

**Usage:**
```bash
streamlit run dashboard.py
# Opens browser at http://localhost:8501
```

---

### `pc_gateway.py` - Gateway Service (23.4 KB)
**Optional** command-line interface cho automation/testing:
- Database logging (SQLite)
- One-shot commands
- Stdin mode (for fake_device testing)

**Usage:**
```bash
# List available ports
python pc_gateway.py

# Connect to specific port
python pc_gateway.py --port COM11 --baud 115200

# One-shot valve control
python pc_gateway.py --port COM11 --send open
python pc_gateway.py --port COM11 --send closed

# Test with fake device
python fake_device.py --mode console | python pc_gateway.py --stdin
```

**Note:** Dashboard không phụ thuộc vào `pc_gateway.py`. Gateway chỉ cần thiết cho:
- CLI automation scripts
- Database logging yêu cầu
- Testing với fake_device

---

### `scan_COM11.py` - Diagnostic Tool (7.9 KB)
**Universal scanner** thay thế `test_serial.py` và `test_COM11_baudrates.py`.

**Usage:**
```bash
# Scan default port (COM11) all baudrates
python scan_COM11.py

# Scan specific port
python scan_COM11.py COM11

# Test single baudrate
python scan_COM11.py COM11 115200

# Scan ALL available ports
python scan_COM11.py --all
```

**Output:**
```
🎯 RECOMMENDED: JLink CDC UART @ 115200 baud
   Score: 17
Sample messages:
  1. @DATA {"flow":0,"valve":"open","battery":0}
  2. @INFO {"node_id":"0x0000FFFE","eui64":"0000000000000052",...}
```

**Use cases:**
- Không biết COM port nào
- Không biết baudrate (38400 vs 115200?)
- Verify firmware đang gửi data
- Troubleshooting connection issues

---

## 🎯 Demo Workflow (10 phút)

Xem chi tiết trong [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md)

**Quick version:**
1. Plug Coordinator USB → PC
2. Run `.\run_dashboard.bat`
3. Click "CONNECT NOW" (auto-detected COM11 @ 115200)
4. Demo:
   - Live telemetry chart
   - Open/Close valve
   - Binding setup
   - Response inspector
5. Disconnect → Done!

---

## 🔌 UART Protocol (Reference)

### PC → Coordinator
```json
@CMD {"id":1,"op":"valve_set","value":"open"}
@CMD {"id":2,"op":"bind_set","index":0,"cluster":"0x0006",...}
@CMD {"id":3,"op":"net_form","pan_id":"0xbeef","ch":11}
```

### Coordinator → PC
```json
@DATA {"flow":55,"valve":"closed","battery":83}
@ACK {"id":1,"ok":true,"msg":"valve opened"}
@INFO {"node_id":"0x0000FFFE","eui64":"...", "pan_id":"0xBEEF",...}
@LOG {"event":"net_cfg","src":"boot","pan_id":"0xBEEF",...}
```

**Rules:**
- Mỗi dòng = 1 message độc lập
- JSON payload sau prefix `@TYPE `
- Dashboard ignore malformed lines (không crash)
- Command ID auto-increment (tracking @ACK)

---

## 🐛 Troubleshooting

### Port Busy / Access Denied
```bash
# Kill existing Python/Streamlit processes
taskkill /F /IM python.exe
taskkill /F /IM streamlit.exe
```

### No Data Received
```bash
# Verify baudrate với scan tool
python scan_COM11.py COM11

# Expected: 115200 baud, score > 0
```

### Wrong COM Port Selected
1. Sidebar → Expand "🔎 Auto-Detect"
2. Click "Start Scan"
3. Sử dụng recommended port/baud

### Dashboard Won't Start
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Check Streamlit version
streamlit --version  # Should be >= 1.29.0
```

---

## 📊 System Requirements

- **Python:** 3.8+
- **OS:** Windows 10/11 (tested), Linux/Mac (should work)
- **Hardware:** USB Zigbee Coordinator (JLink CDC UART)
- **Dependencies:** See `requirements.txt`
  - streamlit >= 1.29.0
  - streamlit-autorefresh >= 0.0.1
  - pyserial >= 3.5
  - pandas >= 2.1.0
  - plotly >= 5.18.0

---

## 🔄 Migration Notes (Cleanup)

**Files REMOVED** (consolidated into `scan_COM11.py`):
- ~~test_serial.py~~ - Basic baudrate test
- ~~test_COM11_baudrates.py~~ - COM11-specific test

**Why consolidated?**
- Giảm confusion (1 tool duy nhất)
- `scan_COM11.py` hỗ trợ ANY port + ALL baudrates
- Smarter detection logic (scoring system)

**Backward compatible:**
```bash
# Old way:
python test_COM11_baudrates.py

# New way (same result):
python scan_COM11.py COM11
```

---

## 🚧 Future Enhancements

- [ ] CSV export telemetry data
- [ ] Alert system (flow > threshold → notification)
- [ ] Auto/Manual mode toggle
- [ ] Multi-device dashboard (multiple sensors/valves)
- [ ] Historical data playback
- [ ] WebSocket API cho external integrations

---

## 📝 Testing

### Manual Test với Fake Device
```bash
# Terminal 1: Run fake device
cd ..
python fake_device.py --mode console

# Terminal 2: Connect gateway via stdin
cd Dashboard_Coordinator
python pc_gateway.py --stdin
```

### Integration Test
```bash
# Real hardware test
python scan_COM11.py          # Verify connection
streamlit run dashboard.py    # Full UI test
```

---

## 📞 Support & Docs

- **Demo Guide:** [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md)
- **UART Protocol:** [../doc/CLI_COMMANDS_REFERENCE.md](../doc/CLI_COMMANDS_REFERENCE.md)
- **Copilot Instructions:** [../.github/copilot-instructions.md](../.github/copilot-instructions.md)

---

**Recommended for DEMO:**
1. Start here → [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md)
2. Run `scan_COM11.py` first (verify hardware)
3. Use `run_dashboard.bat` (auto-cleanup COM ports)
4. Keep `pc_gateway.py` for advanced CLI use
