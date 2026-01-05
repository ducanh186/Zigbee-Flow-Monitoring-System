import json
import re
import threading
import time
from collections import deque
from datetime import datetime
from queue import Queue, Empty

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import serial
from serial.tools import list_ports


# ==============================================================================
# 1. LOGIC & HELPERS
# ==============================================================================
def list_serial_ports():
    return [(p.device, p.description) for p in list_ports.comports()]


def _parse_prefixed_json(line: str, prefix: str):
    if not line:
        return None
    s = line.strip()
    if not s:
        return None

    if not s.upper().startswith(prefix.upper() + " "):
        return None

    payload = s[len(prefix) + 1 :].strip()
    try:
        obj = json.loads(payload)
        return obj
    except json.JSONDecodeError:
        return None


def parse_data_line(line: str):
    obj = _parse_prefixed_json(line, "@DATA")
    if obj is None:
        return None

    flow = int(obj.get("flow", 0))
    battery = int(obj.get("battery", 0))
    valve = str(obj.get("valve", "unknown")).lower()
    if valve == "close":
        valve = "closed"

    mode = str(obj.get("mode", "unknown")).lower()
    if mode not in ("auto", "manual"):
        mode = "unknown"

    return {
        "ts": datetime.now(),
        "flow": flow,
        "battery": battery,
        "valve": valve,
        "mode": mode,
    }


def parse_ack_line(line: str):
    obj = _parse_prefixed_json(line, "@ACK")
    if obj is None:
        return None
    obj["_ts"] = datetime.now()
    return obj


def parse_info_line(line: str):
    obj = _parse_prefixed_json(line, "@INFO")
    if obj is None:
        return None
    obj["_ts"] = datetime.now()
    return obj


def parse_log_line(line: str):
    obj = _parse_prefixed_json(line, "@LOG")
    if obj is None:
        return None
    obj["_ts"] = datetime.now()
    return obj


def make_cmd(op: str, cmd_id: int, **kwargs) -> str:
    payload = {"id": cmd_id, "op": op}
    payload.update(kwargs)
    # Use CLI command "json" to bypass CLI's "No command found" error
    # Format: json {"id":N,"op":"..."}
    return "json " + json.dumps(payload, separators=(',', ':')) + "\r\n"


def normalize_eui64(s: str):
    hex_only = re.sub(r"[^0-9a-fA-F]", "", s or "")
    if len(hex_only) != 16:
        return None
    return hex_only.upper()

def normalize_nodeid(s: str):
    # Ensure format 0x1234
    val = s.strip()
    if not val.lower().startswith("0x"):
        val = "0x" + val
    return val

# -----------------------------
# Auto-detect helpers
# -----------------------------
DEFAULT_BAUD_CANDIDATES = [38400, 115200, 57600, 19200, 9600, 230400]
DEFAULT_PROBE_SECONDS = 0.8


def _probe_port_baud(port: str, baud: int, probe_seconds: float = DEFAULT_PROBE_SECONDS,
                    max_lines: int = 80):
    score = 0
    counts = {"data": 0, "ack": 0, "info": 0, "log": 0, "other_at": 0, "lines": 0, "bytes": 0}
    samples = []

    ser = None
    try:
        ser = serial.Serial(port=port, baudrate=int(baud), timeout=0.15, write_timeout=0.2)
        start = time.time()

        while (time.time() - start) < float(probe_seconds) and counts["lines"] < max_lines:
            raw = ser.readline()
            if not raw:
                continue

            counts["bytes"] += len(raw)
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            counts["lines"] += 1

            rec = parse_data_line(line)
            if rec is not None:
                counts["data"] += 1
                score += 10
                if len(samples) < 3:
                    samples.append(line[:120])
                if counts["data"] >= 2:
                    break
                continue

            ack = parse_ack_line(line)
            if ack is not None:
                counts["ack"] += 1
                score += 5
                if len(samples) < 3:
                    samples.append(line[:120])
                continue

            info = parse_info_line(line)
            if info is not None:
                counts["info"] += 1
                score += 2
                if len(samples) < 3:
                    samples.append(line[:120])
                continue

            log = parse_log_line(line)
            if log is not None:
                counts["log"] += 1
                score += 2
                if len(samples) < 3:
                    samples.append(line[:120])
                continue

            if line.startswith("@"):
                counts["other_at"] += 1
                score += 1
                if len(samples) < 2:
                    samples.append(line[:120])

        return {"score": score, "counts": counts, "samples": samples, "error": ""}

    except Exception as e:
        return {"score": -1, "counts": counts, "samples": samples, "error": f"{type(e).__name__}: {e}"}

    finally:
        try:
            if ser is not None:
                ser.close()
        except Exception:
            pass


def auto_detect_port_and_baud(port_list, baud_list=None, probe_seconds: float = DEFAULT_PROBE_SECONDS):
    baud_list = baud_list or DEFAULT_BAUD_CANDIDATES
    all_reports = []
    best = None 

    for port, desc in port_list:
        for baud in baud_list:
            rep = _probe_port_baud(port, baud, probe_seconds=probe_seconds)
            rep_meta = {"port": port, "desc": desc, "baud": baud, **rep}
            all_reports.append(rep_meta)

            if best is None or rep_meta["score"] > best[0]:
                best = (rep_meta["score"], port, baud, rep_meta)

    if best is None:
        return (None, None, None, all_reports)

    _, best_port, best_baud, best_rep = best
    if best_rep["score"] <= 0:
        return (None, None, best_rep, all_reports)

    return (best_port, int(best_baud), best_rep, all_reports)


def reader_thread_fn(port, baud, stop_event, tx_queue: Queue,
                    data_buf: deque, rx_log: deque, state_dict: dict, lock: threading.Lock):
    ser = None
    try:
        ser = serial.Serial(port=port, baudrate=baud, timeout=0.2, write_timeout=0.2)

        with lock:
            state_dict["connected"] = True
            state_dict["last_error"] = ""
            state_dict["connected_since"] = datetime.now()
            state_dict["lines_total"] = 0
            state_dict["data_total"] = 0
            state_dict["ack_total"] = 0
            state_dict["info_total"] = 0
            state_dict["log_total"] = 0
            state_dict["tx_total"] = 0
            state_dict["last_data_ts"] = None
            state_dict["last_ack_ts"] = None
            state_dict["last_info_ts"] = None
            state_dict["last_log_ts"] = None
            state_dict["last_ack"] = None
            state_dict["last_info"] = None
            state_dict["last_log"] = None

        while not stop_event.is_set():
            # 1) TX
            while True:
                try:
                    out_line = tx_queue.get_nowait()
                except Empty:
                    break
                try:
                    ser.write(out_line.encode("utf-8", errors="ignore"))
                    ser.flush()
                    with lock:
                        state_dict["tx_total"] += 1
                except Exception as e:
                    with lock:
                        state_dict["last_error"] = f"TX {type(e).__name__}: {e}"

            # 2) RX
            raw = ser.readline()
            if raw:
                try:
                    line = raw.decode("utf-8", errors="ignore")
                except Exception:
                    line = ""

                if line:
                    with lock:
                        state_dict["lines_total"] += 1
                        rx_log.appendleft(line.strip())

                    rec = parse_data_line(line)
                    if rec is not None:
                        with lock:
                            data_buf.append(rec)
                            state_dict["data_total"] += 1
                            state_dict["last_data_ts"] = rec["ts"]
                            if "mode" in rec:
                                state_dict["current_mode"] = rec["mode"]
                            if "valve" in rec:
                                state_dict["current_valve"] = rec["valve"]
                        continue

                    ack = parse_ack_line(line)
                    if ack is not None:
                        with lock:
                            state_dict["ack_total"] += 1
                            state_dict["last_ack_ts"] = ack["_ts"]
                            state_dict["last_ack"] = ack
                        continue

                    info = parse_info_line(line)
                    if info is not None:
                        with lock:
                            state_dict["info_total"] += 1
                            state_dict["last_info_ts"] = info["_ts"]
                            state_dict["last_info"] = info
                            # Auto-capture NodeID if present for convenience
                            if "node_id" in info:
                                state_dict["suggested_node_id"] = info["node_id"]
                            if "eui64" in info:
                                state_dict["suggested_eui64"] = info["eui64"]
                        continue

                    log = parse_log_line(line)
                    if log is not None:
                        with lock:
                            state_dict["log_total"] = state_dict.get("log_total", 0) + 1
                            state_dict["last_log_ts"] = log["_ts"]
                            state_dict["last_log"] = log
                        continue

            time.sleep(0.01)

    except Exception as e:
        with lock:
            state_dict["last_error"] = f"{type(e).__name__}: {e}"
            state_dict["connected"] = False
    finally:
        try:
            if ser is not None:
                ser.close()
        except Exception:
            pass
        with lock:
            state_dict["connected"] = False


# ==============================================================================
# 2. STREAMLIT UI SETUP
# ==============================================================================
st.set_page_config(
    page_title="Zigbee Gateway Operator", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="collapsed"
)

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    .stApp { background-color: #0d1117; }
    h1 { font-family: 'Segoe UI', sans-serif; font-weight: 700; color: #e6edf3; margin-bottom: 0.5rem; }
    
    /* Control Section */
    .control-section {
        background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
        border: 2px solid #58a6ff;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 4px 12px rgba(88, 166, 255, 0.15);
        margin-bottom: 15px;
    }
    .control-title { color: #58a6ff; font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; text-align: center; }
    
    /* Valve Status */
    .valve-status-large { text-align: center; padding: 10px; border-radius: 6px; background-color: #161b22; border: 1px solid #30363d; }
    .status-icon-big { font-size: 32px; margin-bottom: 3px; }
    .status-text-big { font-size: 20px; font-weight: 700; margin: 3px 0; }
    
    /* Footer */
    .footer-metrics { background-color: #161b22; border-top: 1px solid #30363d; padding: 10px 20px; margin-top: 30px; border-radius: 8px; }
    .footer-metrics [data-testid="stMetricLabel"] { font-size: 11px !important; color: #6e7681 !important; }
    .footer-metrics [data-testid="stMetricValue"] { font-size: 16px !important; color: #8b949e !important; }
    
    /* Info Cards */
    .info-card { background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 20px; text-align: center; height: 100%; transition: border-color 0.2s; }
    .info-card:hover { border-color: #58a6ff; }
    .stat-label { color: #8b949e; font-size: 13px; font-weight: 600; text-transform: uppercase; }
    .stat-value { font-size: 22px; font-weight: 700; color: #e6edf3; }
    
    /* Tabs & Containers */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] { height: 40px; background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px; color: #8b949e; font-weight: 600; padding: 0 16px; }
    .stTabs [aria-selected="true"] { background-color: #1f6feb !important; color: white !important; border-color: #1f6feb !important; }
    div[data-testid="stVerticalBlockBorderWrapper"] { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; }
    
    /* Alerts */
    .alert-box { padding: 10px; border-radius: 5px; font-weight: bold; margin-bottom: 10px; }
    .alert-error { background-color: #da3633; color: white; }
    .alert-success { background-color: #238636; color: white; }
</style>
""", unsafe_allow_html=True)

# Session state init
if "data_buf" not in st.session_state: st.session_state.data_buf = deque(maxlen=800)
if "rx_log" not in st.session_state: st.session_state.rx_log = deque(maxlen=300)
if "stop_event" not in st.session_state: st.session_state.stop_event = threading.Event()
if "thread" not in st.session_state: st.session_state.thread = None
if "lock" not in st.session_state: st.session_state.lock = threading.Lock()
if "tx_queue" not in st.session_state: st.session_state.tx_queue = Queue()
if "cmd_id" not in st.session_state: st.session_state.cmd_id = 1
if "rt_state" not in st.session_state:
    st.session_state.rt_state = {
        "connected": False, "connected_since": None,
        "last_data_ts": None, "last_ack_ts": None, "last_info_ts": None, "last_log_ts": None,
        "lines_total": 0, "data_total": 0, "ack_total": 0, "info_total": 0, "log_total": 0, "tx_total": 0,
        "last_error": "", "last_ack": None, "last_info": None, "last_log": None,
        "current_mode": None, "current_valve": None,
        "suggested_node_id": None, "suggested_eui64": None
    }
if "serial_port" not in st.session_state: st.session_state.serial_port = ""
if "baudrate" not in st.session_state: st.session_state.baudrate = 38400

# Debounce tracking for UI actions
if "last_mode_change_ts" not in st.session_state: st.session_state.last_mode_change_ts = 0
if "last_valve_cmd_ts" not in st.session_state: st.session_state.last_valve_cmd_ts = 0
DEBOUNCE_MS = 800  # Minimum interval between commands

def next_cmd_id():
    st.session_state.cmd_id += 1
    return st.session_state.cmd_id

def send_cmd_line(line: str):
    st.session_state.tx_queue.put(line)

# ==============================================================================
# 3. SIDEBAR
# ==============================================================================
st.sidebar.title("🎛️ Control Panel")
ports = list_serial_ports()
port_options = [p[0] for p in ports] if ports else []

# Auto-select port
if not st.session_state.rt_state["connected"] and not st.session_state.serial_port and port_options:
    st.session_state.serial_port = port_options[0]

with st.sidebar.container(border=True):
    if st.session_state.rt_state["connected"]:
        st.success(f"✅ SYSTEM ONLINE")
        if st.session_state.rt_state['connected_since']:
            duration = datetime.now() - st.session_state.rt_state['connected_since']
            st.metric("Uptime", str(duration).split('.')[0])
        st.code(f"{st.session_state.serial_port} @ {st.session_state.baudrate}", language="text")
        
        if st.button("⏹ DISCONNECT", type="primary", width="stretch"):
            st.session_state.stop_event.set()
            time.sleep(0.2)
            with st.session_state.lock:
                st.session_state.rt_state["connected"] = False
            st.rerun()
    else:
        st.markdown("**🔌 Connection Setup**")
        st.session_state.serial_port = st.selectbox("Port", options=port_options, index=0 if port_options else None)
        st.session_state.baudrate = st.selectbox("Baud", options=[115200, 38400, 9600], index=0)

        if st.button("▶ CONNECT NOW", type="primary", width="stretch", disabled=not ports):
            if st.session_state.thread and st.session_state.thread.is_alive():
                st.session_state.stop_event.set()
                st.session_state.thread.join(timeout=1)

            st.session_state.stop_event.clear()
            st.session_state.data_buf.clear()
            st.session_state.rx_log.clear()

            t = threading.Thread(
                target=reader_thread_fn,
                args=(st.session_state.serial_port, int(st.session_state.baudrate), st.session_state.stop_event,
                      st.session_state.tx_queue, st.session_state.data_buf, st.session_state.rx_log,
                      st.session_state.rt_state, st.session_state.lock),
                daemon=True
            )
            st.session_state.thread = t
            t.start()
            time.sleep(0.2)
            st.rerun()

# Display Settings
st.sidebar.divider()
with st.sidebar.expander("⚙️ Display Settings"):
    auto_refresh_ms = st.slider("Refresh (ms)", 200, 3000, 800, 100)
    show_table = st.toggle("Show Raw Data", value=True)
    show_log = st.toggle("Show Terminal", value=True)

# State Snapshots
with st.session_state.lock:
    rt = dict(st.session_state.rt_state)
    data_copy = list(st.session_state.data_buf)
    log_copy = list(st.session_state.rx_log)
    last_ack = rt.get("last_ack")
    last_info = rt.get("last_info")
    last_log = rt.get("last_log")

if rt["connected"]:
    st_autorefresh(interval=auto_refresh_ms, key="datarefresh")

# ==============================================================================
# HEADER
# ==============================================================================
h_col1, h_col2 = st.columns([5, 1])
with h_col1: st.title("📡 Zigbee Gateway Operator")
with h_col2:
    status_color = "#238636" if rt['connected'] else "#da3633"
    st.markdown(f'<div style="margin-top:18px;background:{status_color}33;color:{status_color};padding:6px 18px;border-radius:20px;border:1px solid {status_color};text-align:center;font-weight:bold;">{"● ONLINE" if rt["connected"] else "● OFFLINE"}</div>', unsafe_allow_html=True)

# ==============================================================================
# PRIORITY: VALVE CONTROL
# ==============================================================================
valve_state = None
mode_state = None
if data_copy:
    valve_state = str(data_copy[-1].get("valve", "")).lower() or None
    mode_state = str(data_copy[-1].get("mode", "")).lower() or None
    if mode_state not in ("auto", "manual"): mode_state = None

st.markdown('<div class="control-section"><div class="control-title">🎮 Valve Control Center</div>', unsafe_allow_html=True)
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 4])

with ctrl_col1:
    v_color = "#238636" if valve_state == "open" else "#da3633"
    v_icon = "💧" if valve_state == "open" else "🚫"
    st.markdown(f'<div class="valve-status-large"><div class="status-icon-big">{v_icon}</div><div class="status-text-big" style="color:{v_color};">{str(valve_state).upper() if valve_state else "UNKNOWN"}</div><div style="font-size:12px;color:#8b949e;">VALVE STATUS</div></div>', unsafe_allow_html=True)

with ctrl_col2:
    # Show current confirmed mode from device
    m_color = "#58a6ff" if mode_state == "auto" else "#8b949e"
    m_icon = "🤖" if mode_state == "auto" else "🎮"
    st.markdown(f'<div class="valve-status-large"><div class="status-icon-big">{m_icon}</div><div class="status-text-big" style="color:{m_color};">{str(mode_state).upper() if mode_state else "UNKNOWN"}</div><div style="font-size:12px;color:#8b949e;">CURRENT MODE</div></div>', unsafe_allow_html=True)

with ctrl_col3:
    st.caption("🕹️ CONTROL PANEL")
    
    # Sync UI mode with confirmed device mode
    confirmed_mode = mode_state or "manual"
    
    # Mode selector - use confirmed mode as default
    mode_options = ["manual", "auto"]
    current_idx = mode_options.index(confirmed_mode) if confirmed_mode in mode_options else 0
    
    col_mode1, col_mode2 = st.columns(2)
    
    # Debounce check
    now_ms = int(time.time() * 1000)
    can_change_mode = (now_ms - st.session_state.last_mode_change_ts) > DEBOUNCE_MS
    can_send_valve = (now_ms - st.session_state.last_valve_cmd_ts) > DEBOUNCE_MS
    
    with col_mode1:
        if st.button("🎮 MANUAL", use_container_width=True, 
                     disabled=not (rt["connected"] and can_change_mode) or mode_state == "manual",
                     type="primary" if mode_state == "manual" else "secondary"):
            cid = next_cmd_id()
            send_cmd_line(make_cmd("mode_set", cid, value="manual"))
            st.session_state.last_mode_change_ts = now_ms
            st.toast("Switching to MANUAL mode...")
    
    with col_mode2:
        if st.button("🤖 AUTO", use_container_width=True,
                     disabled=not (rt["connected"] and can_change_mode) or mode_state == "auto",
                     type="primary" if mode_state == "auto" else "secondary"):
            cid = next_cmd_id()
            send_cmd_line(make_cmd("mode_set", cid, value="auto"))
            st.session_state.last_mode_change_ts = now_ms
            st.toast("Switching to AUTO mode...")
    
    st.divider()
    
    # Valve buttons - only enabled in MANUAL mode
    manual_enabled = (mode_state == "manual")
    btn_col1, btn_col2 = st.columns(2)
    
    with btn_col1:
        if st.button("🟢 OPEN VALVE", use_container_width=True, 
                     disabled=not (rt["connected"] and manual_enabled and can_send_valve),
                     type="primary" if valve_state == "open" else "secondary"):
            cid = next_cmd_id()
            send_cmd_line(make_cmd("valve_set", cid, value="open"))
            st.session_state.last_valve_cmd_ts = now_ms
            st.toast("Opening valve...")
    
    with btn_col2:
        if st.button("🔴 CLOSE VALVE", use_container_width=True,
                     disabled=not (rt["connected"] and manual_enabled and can_send_valve),
                     type="primary" if valve_state == "closed" else "secondary"):
            cid = next_cmd_id()
            send_cmd_line(make_cmd("valve_set", cid, value="closed"))
            st.session_state.last_valve_cmd_ts = now_ms
            st.toast("Closing valve...")
    
    if mode_state == "auto":
        st.info("💡 Switch to MANUAL mode to control valve")

st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# MONITORING
# ==============================================================================
if data_copy:
    df = pd.DataFrame(data_copy)
    df["ts"] = pd.to_datetime(df["ts"])
    latest = df.iloc[-1]
else:
    df = pd.DataFrame()
    latest = None

col_info, col_chart = st.columns([2, 8])
with col_info:
    if latest is not None:
        st.markdown(f'<div class="info-card"><div class="stat-label">⚙️ Current Mode</div><div class="stat-value" style="color:#58a6ff;">{str(mode_state).upper()}</div></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown(f'<div class="info-card"><div class="stat-label">🌊 Flow Rate</div><div class="stat-value" style="color:#29b5e8;">{int(latest["flow"])} L/m</div></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown(f'<div class="info-card"><div class="stat-label">🔋 Battery</div><div class="stat-value" style="color:#00E676;">{int(latest["battery"])} %</div></div>', unsafe_allow_html=True)

with col_chart:
    if not df.empty:
        tab_flow, tab_batt = st.tabs(["🌊 Flow Chart", "🔋 Battery Chart"])
        common_layout = dict(height=350, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(showgrid=False), showlegend=False)
        
        with tab_flow:
            fig = px.area(df, x='ts', y='flow', template="plotly_dark")
            fig.update_traces(line_color='#29b5e8', fillcolor='rgba(41, 181, 232, 0.2)')
            fig.update_layout(**common_layout)
            st.plotly_chart(fig, use_container_width=True)
            
        with tab_batt:
            fig = px.line(df, x='ts', y='battery', template="plotly_dark")
            fig.update_traces(line_color='#00E676', line_width=3)
            fig.update_layout(**common_layout)
            st.plotly_chart(fig, use_container_width=True)

# ==============================================================================
# CONFIG TABS (UPDATED)
# ==============================================================================
st.write("")
st.markdown("### 🛠️ Configuration & Diagnostics")
tab_pair, tab_diag, tab_net, tab_raw = st.tabs(["🔗 Pairing (Fix 0xC8)", "🩺 Diagnostics", "🌐 Network", "📝 Raw Data"])

# --- TAB 1: PAIRING (CRITICAL FIX) ---
with tab_pair:
    st.info("💡 **Fix for 'Discovery Failed':** You must provide the NodeID (Short Address) so the Coordinator can update its binding table.")
    
    c1, c2, c3 = st.columns([3, 2, 2])
    
    # Auto-fill if available from @INFO
    def_eui = rt.get("suggested_eui64", "")
    def_node = rt.get("suggested_node_id", "")
    
    p_eui = c1.text_input("Valve EUI64 (MAC)", value=def_eui, placeholder="000D6F...")
    p_node = c2.text_input("Valve NodeID (Hex)", value=def_node, placeholder="0x1A2B")
    
    c3.write("")
    c3.write("")
    if c3.button("🔗 PAIR VALVE (Fix Route)", type="primary", use_container_width=True, disabled=not rt["connected"]):
        if len(p_eui) < 16 or not p_node.startswith("0x"):
            st.error("Invalid Input: Check EUI64 length or NodeID format (0x...)")
        else:
            cid = next_cmd_id()
            # UPDATED COMMAND: valve_pair with NodeID
            send_cmd_line(make_cmd("valve_pair", cid, index=0, eui64=p_eui, node_id=p_node, src_ep=2, dst_ep=1, cluster="0x0006"))
            st.success(f"Sent Pairing Command (ID={cid}) with NodeID {p_node}")

# --- TAB 2: DIAGNOSTICS (NEW) ---
with tab_diag:
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.caption("Latest Radio Event (@LOG)")
        if last_log:
            st_val = last_log.get("st", "??")
            meaning = "Unknown"
            bg_col = "#30363d"
            
            if st_val == "0x00": 
                meaning = "SUCCESS (Delivered)"; bg_col = "#238636"
            elif st_val == "0xC8": 
                meaning = "ID_DISCOVERY_FAILED (Missing NodeID)"; bg_col = "#da3633"
            elif st_val == "0xCF": 
                meaning = "NO_ACTIVE_ROUTE (Unreachable)"; bg_col = "#9e6a03"
            
            st.markdown(f"""
            <div style="background:{bg_col}; padding:15px; border-radius:8px; text-align:center;">
                <div style="font-size:24px; font-weight:bold;">{st_val}</div>
                <div>{meaning}</div>
                <div style="font-size:12px; margin-top:5px; opacity:0.8;">{last_log.get('event','')}</div>
            </div>
            """, unsafe_allow_html=True)
            
            if st_val == "0xC8":
                st.warning("👉 Go to 'Pairing' tab and re-enter NodeID to fix this.")
            elif st_val == "0xCF":
                st.warning("👉 Device might be asleep or has changed NodeID. Try waking it up.")
        else:
            st.info("No radio logs received yet.")

    with col_d2:
        st.caption("Latest ACK")
        if last_ack:
            ok = last_ack.get("ok", False)
            st.code(f"ID: {last_ack.get('id')}\nMSG: {last_ack.get('msg')}\nOK: {ok}", language="yaml")
        
        if st.button("Request Device Info (@INFO)"):
            cid = next_cmd_id()
            send_cmd_line(make_cmd("info", cid))

# --- TAB 3: NETWORK ---
with tab_net:
    nc1, nc2, nc3 = st.columns(3)
    pan = nc1.text_input("PAN ID", "0xbeef")
    ch = nc2.number_input("Channel", 11, 26, 11)
    if nc3.button("Re-Form Network"):
        cid = next_cmd_id()
        send_cmd_line(make_cmd("net_form", cid, pan_id=pan, ch=int(ch), tx_power=20, force=1))

# --- TAB 4: RAW ---
with tab_raw:
    rc1, rc2 = st.columns(2)
    with rc1:
        if show_table: st.dataframe(df.tail(20), use_container_width=True)
    with rc2:
        if show_log: st.text_area("Terminal Log", value="\n".join(log_copy), height=300)

# --- FOOTER ---
st.markdown('<div class="footer-metrics">', unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("RX Lines", rt.get("lines_total", 0))
c2.metric("TX Cmds", rt.get("tx_total", 0))
c3.metric("Data Pkts", rt.get("data_total", 0))
c4.metric("Last Error", rt.get("last_error") or "None")
st.markdown('</div>', unsafe_allow_html=True)