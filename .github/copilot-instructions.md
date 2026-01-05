
# Copilot / GitHub Agent Instructions

Purpose: Provide concise, actionable guidance to AI coding agents working on the Zigbee Flow Monitoring System. Focus on Python dashboard, utilities, and PC-side tooling; DO NOT modify firmware C code.

---

## 🎯 Project Overview

**System:** Zigbee-based water flow monitoring + automated valve control  
**Architecture:** 3-node Zigbee network (Coordinator, Sensor, Valve) + PC Dashboard  
**Your Scope:** PC-side Python code ONLY

### Components You Own:
- `Dashboard_Coordinator/dashboard.py` - Streamlit UI (27KB, real-time monitoring + control)
- `Dashboard_Coordinator/pc_gateway.py` - CLI gateway with SQLite logging (23KB, optional)
- `Dashboard_Coordinator/scan_com10.py` - Port/baud diagnostic tool

### Components You MUST NOT Edit:
- `Coordinator_Node/app.c` - Zigbee Coordinator firmware (C/Simplicity Studio)
- `Sensor_Node/app.c` - Flow sensor firmware
- `Vavle_Node/app.c` - Valve actuator firmware

**If firmware changes are needed:** Write a "Change Request" document with target files, function names, expected UART output, and test steps. Do NOT edit `.c` or `.h` files.

---

## 🔌 UART Protocol Contract (CRITICAL)

The PC dashboard MUST adhere to this exact protocol:

### PC ← Coordinator (RX)
```
@DATA {"flow":120,"battery":90,"valve":"open","mode":"auto"}
@ACK {"id":1,"ok":true,"msg":"valve opened","valve":"open"}
@INFO {"node_id":"0x1A2B","eui64":"000D6F000F1A2B3C","pan":"0xBEEF","ch":15}
@LOG {"event":"TX","st":"0x00","dest":"0x1A2B"}
```

### PC → Coordinator (TX)
```
@CMD {"id":1,"op":"valve_set","value":"open"}
@CMD {"id":2,"op":"mode_set","value":"auto"}
@CMD {"id":3,"op":"valve_pair","index":0,"eui64":"...","node_id":"0x1A2B","src_ep":2,"dst_ep":1,"cluster":"0x0006"}
@CMD {"id":4,"op":"net_form","pan_id":"0xBEEF","ch":15,"tx_power":20,"force":1}
```

### Critical Operations:
- `valve_set` - Open/close valve (value: "open"|"closed")
- `valve_pair` - Fix binding (MUST include `node_id` to resolve 0xC8 error)
- `mode_set` - Auto/manual mode (value: "auto"|"manual")
- `net_form` - Reform network with custom PAN/channel

### Parsing Rules:
1. Each line is independent - continue on malformed JSON (never crash UI)
2. Use `_parse_prefixed_json(line, prefix)` helper (see [dashboard.py](Dashboard_Coordinator/dashboard.py#L30-L42))
3. Normalize `valve:"close"` → `"closed"` for consistency
4. Always increment command ID (`next_cmd_id()`)

---

## 🧵 Streamlit Architecture Pattern

**Key Constraint:** Streamlit reruns from top on every interaction. Use session state + background thread.

### Critical Pattern (from dashboard.py):
```python
# Session state (persists across reruns)
if "data_buf" not in st.session_state: 
    st.session_state.data_buf = deque(maxlen=800)
if "thread" not in st.session_state: 
    st.session_state.thread = None
if "lock" not in st.session_state: 
    st.session_state.lock = threading.Lock()

# Background thread reads serial, populates data_buf
def reader_thread_fn(port, baud, stop_event, tx_queue, data_buf, rx_log, state_dict, lock):
    with serial.Serial(port, baud) as ser:
        while not stop_event.is_set():
            line = ser.readline().decode()
            rec = parse_data_line(line)
            if rec:
                with lock: data_buf.append(rec)

# UI uses st_autorefresh for live updates
if rt["connected"]:
    st_autorefresh(interval=800, key="datarefresh")
```

### DO:
- Use `threading.Lock()` for all shared state mutations
- Put TX commands in `Queue` (thread-safe)
- Use `st_autorefresh` for live data (not `time.sleep`)

### DON'T:
- Block main thread with `serial.read()` loops
- Modify session state without lock in thread
- Use global variables (Streamlit won't preserve them)

---

## 🐛 Common Zigbee Errors & Fixes

### Error 0xC8 (ID_DISCOVERY_FAILED)
**Root Cause:** Binding table entry missing remote `NodeID` (only has EUI64)  
**Fix in UI:** Pairing tab → Enter both EUI64 AND NodeID → Send `valve_pair` command  
**Implementation:** See [dashboard.py](Dashboard_Coordinator/dashboard.py#L579-L602) pairing tab

### Error 0xCF (NO_ACTIVE_ROUTE)
**Root Cause:** Valve device unreachable (asleep, rejoined with new NodeID)  
**Fix:** Wake device, check network logs, re-pair if NodeID changed

### Status Code Mapping (from @LOG):
```python
if st_val == "0x00": meaning = "SUCCESS (Delivered)"
elif st_val == "0xC8": meaning = "ID_DISCOVERY_FAILED (Missing NodeID)"
elif st_val == "0xCF": meaning = "NO_ACTIVE_ROUTE (Unreachable)"
```
Display this in Diagnostics tab - see [dashboard.py](Dashboard_Coordinator/dashboard.py#L608-L631)

---

## 🚀 Development Workflow

### 1. Quick Start
```bash
cd Dashboard_Coordinator
pip install -r requirements.txt
streamlit run dashboard.py
```

### 2. Testing Without Hardware
Use `fake_device.py` to generate sample UART data:
```bash
python fake_device.py --mode console --interval 2
```

### 3. Debugging Serial Issues
```bash
python scan_com10.py  # Auto-detect port + baudrate
```

### 4. Auto-Detection Logic
Dashboard uses smart port/baud probing (see [dashboard.py](Dashboard_Coordinator/dashboard.py#L115-L165)):
- Tries common bauds: [38400, 115200, 57600, ...]
- Scores responses (10pts for @DATA, 5 for @ACK)
- Best score wins

---

## 📋 Pre-Commit Checklist

Before any PC-side code change:
- [ ] Does NOT modify `.c`, `.h`, or `.sls` files
- [ ] Handles malformed UART lines gracefully (try/except + log)
- [ ] Uses thread lock for shared session state
- [ ] Increments command ID for every @CMD sent
- [ ] Includes both EUI64 + NodeID in pairing commands
- [ ] Tests with `scan_com10.py` for serial connectivity
- [ ] Updates UI preserves existing charts/controls

---

## 📖 Key Files Reference

| File | Purpose | Key Functions/Patterns |
|------|---------|----------------------|
| [dashboard.py](Dashboard_Coordinator/dashboard.py) | Main Streamlit UI | `reader_thread_fn()`, `parse_data_line()`, `make_cmd()`, valve control logic |
| [pc_gateway.py](Dashboard_Coordinator/pc_gateway.py) | CLI gateway + DB | `ZigbeeGateway` class, `_normalize_json()`, `send_command()` |
| [scan_com10.py](Dashboard_Coordinator/scan_com10.py) | Port scanner | Auto-baud detection, @DATA sniffing |
| [CLI_COMMANDS_REFERENCE.md](doc/CLI_COMMANDS_REFERENCE.md) | Zigbee CLI docs | Network formation, binding setup |

---

## 🎨 UI/UX Standards

From current dashboard implementation:
- **GitHub Dark theme** - `#0d1117` background, `#58a6ff` accents
- **Status indicators** - Green (#238636) = success, Red (#da3633) = error
- **Control layout** - Valve controls at top, charts middle, config tabs bottom
- **Metrics** - Use `st.metric()` for counters, custom HTML for status badges

Example status badge pattern:
```python
st.markdown(f'<div style="color:{status_color};">{"● ONLINE" if connected else "● OFFLINE"}</div>', 
            unsafe_allow_html=True)
```

---

## ⚠️ Firmware Coordination (Read-Only Reference)

You can READ firmware code to understand protocol, but never edit:
- `Coordinator_Node/app.c` - Implements @CMD handlers (`emberAfPluginUartMsgCommandHandler`)
- `Vavle_Node/app.c` - Processes On/Off cluster commands
- `Sensor_Node/app.c` - Sends flow/battery reports

**When firmware changes ARE needed:** Document in a Change Request with:
1. Target function names (e.g., `emberAfPluginUartMsgCommandHandler`)
2. Expected new @ACK/@LOG output format
3. Test case using PC dashboard to verify behavior
