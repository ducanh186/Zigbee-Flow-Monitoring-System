import json
import re
import threading
import time
from collections import deque
from datetime import datetime
from queue import Queue, Empty

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import serial
from serial.tools import list_ports


# ==============================================================================
# 1. LOGIC & HELPERS (GIỮ NGUYÊN KHÔNG ĐỔI)
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

    return {
        "ts": datetime.now(),
        "flow": flow,
        "battery": battery,
        "valve": valve,
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
    return "@CMD " + json.dumps(payload) + "\n"


def normalize_eui64(s: str):
    hex_only = re.sub(r"[^0-9a-fA-F]", "", s or "")
    if len(hex_only) != 16:
        return None
    return hex_only.upper()


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
st.set_page_config(page_title="Zigbee Operator Console", layout="wide", page_icon="📡")

# --- CUSTOM CSS (Sửa màu & Phồng chữ) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    h1 { font-family: 'Segoe UI', sans-serif; font-weight: 700; color: #E0E0E0; text-shadow: 0 0 10px rgba(255,255,255,0.1); }
    [data-testid="stMetric"] { background-color: #262626; padding: 15px 20px; border-radius: 10px; border: 1px solid #383838; box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: transform 0.2s; }
    [data-testid="stMetric"]:hover { border-color: #666; transform: translateY(-2px); }
    [data-testid="stMetricLabel"] { font-size: 16px !important; color: #A0A0A0 !important; font-weight: 500; }
    [data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 700 !important; color: #FFFFFF !important; font-family: 'Roboto Mono', monospace; }
    [data-testid="stMetricDelta"] svg { transform: scale(1.2); }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] { height: 55px; background-color: #1E1E1E; border-radius: 8px; color: #B0B0B0; font-weight: 600; border: 1px solid #333; padding: 0 25px; }
    .stTabs [aria-selected="true"] { background-color: #FF4B4B !important; color: white !important; border-color: #FF4B4B !important; box-shadow: 0 0 10px rgba(255, 75, 75, 0.4); }
    .stButton button { font-weight: bold; border-radius: 6px; height: 45px; }
</style>
""", unsafe_allow_html=True)

# Session state init
if "data_buf" not in st.session_state:
    st.session_state.data_buf = deque(maxlen=800)
if "rx_log" not in st.session_state:
    st.session_state.rx_log = deque(maxlen=300)
if "stop_event" not in st.session_state:
    st.session_state.stop_event = threading.Event()
if "thread" not in st.session_state:
    st.session_state.thread = None
if "lock" not in st.session_state:
    st.session_state.lock = threading.Lock()
if "tx_queue" not in st.session_state:
    st.session_state.tx_queue = Queue()
if "cmd_id" not in st.session_state:
    st.session_state.cmd_id = 1
if "rt_state" not in st.session_state:
    st.session_state.rt_state = {
        "connected": False,
        "connected_since": None,
        "last_data_ts": None,
        "last_ack_ts": None,
        "last_info_ts": None,
        "last_log_ts": None,
        "lines_total": 0,
        "data_total": 0,
        "ack_total": 0,
        "info_total": 0,
        "log_total": 0,
        "tx_total": 0,
        "last_error": "",
        "last_ack": None,
        "last_info": None,
        "last_log": None,
    }
if "autodetect_last" not in st.session_state:
    st.session_state.autodetect_last = None
if "serial_port" not in st.session_state:
    st.session_state.serial_port = ""
if "baudrate" not in st.session_state:
    st.session_state.baudrate = 38400

def next_cmd_id():
    st.session_state.cmd_id += 1
    return st.session_state.cmd_id

def send_cmd_line(line: str):
    st.session_state.tx_queue.put(line)

# ==============================================================================
# 3. SIDEBAR (SMART & IMPROVED DESIGN)
# ==============================================================================
st.sidebar.title("🎛️ Control Panel")

# Refresh ports list
ports = list_serial_ports()
port_options = [p[0] for p in ports] if ports else []
port_labels = {p[0]: f"{p[0]} — {p[1]}" for p in ports}

# Auto-select logic for first run
if not st.session_state.rt_state["connected"]:
    if not st.session_state.serial_port:
        if "COM7" in port_options:
            st.session_state.serial_port = "COM7"
        elif port_options:
            st.session_state.serial_port = port_options[0]
    if not st.session_state.baudrate:
        st.session_state.baudrate = 38400

# ---- SECTION A: STATUS & CONNECTION ----
with st.sidebar.container(border=True):
    if st.session_state.rt_state["connected"]:
        # >>>> TRẠNG THÁI: KHI ĐÃ KẾT NỐI
        st.success(f"✅ SYSTEM ONLINE")
        if st.session_state.rt_state['connected_since']:
            duration = datetime.now() - st.session_state.rt_state['connected_since']
            # Format duration nicely H:M:S
            total_seconds = int(duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            st.metric("Uptime", f"{hours:02}:{minutes:02}:{seconds:02}")
        
        st.code(f"{st.session_state.serial_port} @ {st.session_state.baudrate}", language="text")
        
        if st.button("⏹ DISCONNECT", type="primary", use_container_width=True):
            # Trigger disconnect logic
            st.session_state.stop_event.set()
            time.sleep(0.2)
            with st.session_state.lock:
                st.session_state.rt_state["connected"] = False
            st.rerun()

    else:
        # >>>> TRẠNG THÁI: KHI CHƯA KẾT NỐI (HIỆN FORM)
        st.markdown("**🔌 Connection Setup**")
        
        # 1. Manual Connect Form
        sel_port = st.selectbox(
            "Select Port",
            options=port_options,
            index=port_options.index(st.session_state.serial_port) if (st.session_state.serial_port in port_options) else 0,
            format_func=lambda x: port_labels.get(x, x),
            key="serial_port_sel"
        )
        # Update session state from selection
        st.session_state.serial_port = sel_port

        sel_baud = st.selectbox(
            "Baudrate", 
            options=[9600, 19200, 38400, 57600, 115200, 230400, 921600],
            index=[9600, 19200, 38400, 57600, 115200, 230400, 921600].index(int(st.session_state.baudrate)) if int(st.session_state.baudrate) in [9600, 19200, 38400, 57600, 115200, 230400, 921600] else 2,
            key="baud_sel"
        )
        st.session_state.baudrate = sel_baud

        if st.button("▶ CONNECT NOW", type="primary", use_container_width=True, disabled=not ports):
            # Trigger connect logic
            if not st.session_state.serial_port:
                st.error("No port selected")
            else:
                if st.session_state.thread is not None and st.session_state.thread.is_alive():
                    st.session_state.stop_event.set()
                    st.session_state.thread.join(timeout=1)

                st.session_state.stop_event.clear()
                st.session_state.data_buf.clear()
                st.session_state.rx_log.clear()

                t = threading.Thread(
                    target=reader_thread_fn,
                    args=(
                        st.session_state.serial_port,
                        int(st.session_state.baudrate),
                        st.session_state.stop_event,
                        st.session_state.tx_queue,
                        st.session_state.data_buf,
                        st.session_state.rx_log,
                        st.session_state.rt_state,
                        st.session_state.lock,
                    ),
                    daemon=True,
                )
                st.session_state.thread = t
                t.start()
                time.sleep(0.2)
                st.rerun()

        # 2. Auto Detect (Hidden in Expander to keep it clean)
        with st.expander("🔎 Auto-Detect / Trouble?"):
            st.caption("Scan all ports/baudrates if you don't know the settings.")
            baud_candidates = st.multiselect(
                "Scan Bauds",
                options=[9600, 19200, 38400, 57600, 115200, 230400],
                default=[38400, 115200, 57600],
            )
            probe_sec = st.slider("Scan time (s)", 0.3, 2.0, 0.8)
            
            if st.button("Start Scan", use_container_width=True, disabled=not ports):
                with st.spinner("Scanning..."):
                    best_port, best_baud, best_rep, _ = auto_detect_port_and_baud(
                        port_list=ports,
                        baud_list=baud_candidates,
                        probe_seconds=probe_sec
                    )
                if best_port:
                    st.session_state.serial_port = best_port
                    st.session_state.baudrate = int(best_baud)
                    st.success(f"Found: {best_port} @ {best_baud}")
                    st.rerun()
                else:
                    st.warning("No valid signal found.")

# ---- SECTION B: DISPLAY SETTINGS ----
st.sidebar.divider()
with st.sidebar.expander("⚙️ Display Settings", expanded=False):
    auto_refresh_ms = st.slider("UI Refresh Rate (ms)", 200, 3000, 800, 100)
    show_table = st.toggle("Show Raw Data Table", value=True)
    show_log = st.toggle("Show Terminal Log", value=True)

# Read state snapshot (GIỮ NGUYÊN)
with st.session_state.lock:
    rt = dict(st.session_state.rt_state)
    data_copy = list(st.session_state.data_buf)
    log_copy = list(st.session_state.rx_log)
    last_ack = rt.get("last_ack")
    last_info = rt.get("last_info")
    last_log = rt.get("last_log")

# Auto refresh
if rt["connected"]:
    st_autorefresh(interval=auto_refresh_ms, key="datarefresh")

# ==============================================================================
# 4. MAIN DASHBOARD LAYOUT (GIỮ NGUYÊN NHƯ CŨ)
# ==============================================================================

# --- HEADER STATUS ---
st.title("📡 Zigbee Gateway Operator")
st.markdown("---")

# Quick Stats Row
stat_col1, stat_col2, stat_col3, stat_col4, stat_col5 = st.columns(5)
with stat_col1:
    is_connected = rt['connected']
    status_text = "ONLINE" if is_connected else "OFFLINE"
    st.metric(
        "System Status", 
        status_text, 
        delta="Connected" if is_connected else "- Disconnected",
        delta_color="normal" if is_connected else "inverse"
    )

with stat_col2:
    st.metric("RX Lines", f"{rt.get('lines_total', 0):,}")
with stat_col3:
    st.metric("TX Cmds", f"{rt.get('tx_total', 0):,}")
with stat_col4:
    st.metric("Data Pkts", f"{rt.get('data_total', 0):,}")
with stat_col5:
    err = rt.get("last_error", "")
    if err:
        st.error(f"Error: {err}")
    else:
        st.metric("Errors", "None", delta_color="off")

# --- MONITORING SECTION (Chart & Big Numbers) ---
st.subheader("📊 Live Telemetry")

valve_state = None
if data_copy:
    valve_state = str(data_copy[-1].get("valve", "")).lower() or None
    df = pd.DataFrame(data_copy)
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.sort_values("ts")
    latest = df.iloc[-1]
else:
    latest = None

mon_c1, mon_c2 = st.columns([1.2, 2.5])

with mon_c1:
    st.markdown("##### Current State")
    with st.container(border=True):
        if latest is not None:
            v_color = "#00E676" if valve_state == "open" else "#FF5252"
            v_icon = "💧" if valve_state == "open" else "🚫"
            st.markdown(
                f"""
                <div style='text-align: center; margin-bottom: 20px;'>
                    <div style='font-size: 60px;'>{v_icon}</div>
                    <div style='font-size: 28px; font-weight: bold; color: {v_color}; text-transform: uppercase;'>
                        {str(valve_state)}
                    </div>
                    <div style='color: #888; font-size: 14px;'>VALVE STATUS</div>
                </div>
                """, 
                unsafe_allow_html=True
            )
            st.divider()
            c_flow, c_bat = st.columns(2)
            c_flow.metric("Flow Rate", f"{int(latest['flow'])}", "L/min")
            c_bat.metric("Battery", f"{int(latest['battery'])}%", "Volts")
        else:
            st.warning("Waiting for @DATA...")
            st.metric("Flow", "--")
            st.metric("Battery", "--")

with mon_c2:
    if latest is not None:
        tab_flow, tab_bat = st.tabs(["🌊 Flow History", "🔋 Battery History"])
        with tab_flow:
            st.line_chart(df.set_index("ts")[["flow"]], height=280, color="#29b5e8")
        with tab_bat:
            st.line_chart(df.set_index("ts")[["battery"]], height=280, color="#4cd137")
    else:
        st.info("No data available to chart.")

# --- COMMAND CENTER ---
st.markdown("### 🛠️ Command Center")
tab_valve, tab_bind, tab_net, tab_dev = st.tabs([
    "💧 Valve Control", 
    "🔗 Binding Setup", 
    "🌐 Network Config", 
    "ℹ️ Info & Thresholds"
])

# 1. Valve Control Tab
with tab_valve:
    c_v1, c_v2 = st.columns([1, 3])
    with c_v1:
        st.info(f"Current Status: **{str(valve_state).upper() if valve_state else 'UNKNOWN'}**")
    with c_v2:
        col_open, col_close = st.columns(2)
        b_open = col_open.button("🟢 OPEN VALVE", use_container_width=True, disabled=not rt["connected"], type="primary" if valve_state == "open" else "secondary")
        b_close = col_close.button("🔴 CLOSE VALVE", use_container_width=True, disabled=not rt["connected"], type="primary" if valve_state == "closed" else "secondary")
        
        if b_open:
            cid = next_cmd_id()
            send_cmd_line(make_cmd("valve_set", cid, value="open"))
            st.toast(f"Sent OPEN command (id={cid})", icon="✅")

        if b_close:
            cid = next_cmd_id()
            send_cmd_line(make_cmd("valve_set", cid, value="closed"))
            st.toast(f"Sent CLOSE command (id={cid})", icon="✅")

# 2. Binding Tab
with tab_bind:
    st.caption("Configure binding table for valve control via On/Off cluster")
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
    bind_index = b_col1.number_input("Index", 0, 15, 0)
    bind_cluster = b_col2.text_input("Cluster", "0x0006")
    bind_src_ep = b_col3.number_input("Src EP", 1, 240, 2)
    bind_dst_ep = b_col4.number_input("Dst EP", 1, 240, 1)
    
    valve_eui64 = st.text_input("Valve EUI64 (16 hex)", placeholder="000D6F0000AABBCC", help="Copy from Info")
    
    if st.button("Set Binding", type="primary", disabled=not rt["connected"]):
        norm = normalize_eui64(valve_eui64)
        if not norm:
            st.error("Invalid EUI64! Must be 16 hex chars.")
        else:
            cid = next_cmd_id()
            send_cmd_line(make_cmd("bind_set", cid, index=int(bind_index), cluster=str(bind_cluster), 
                                   src_ep=int(bind_src_ep), dst_ep=int(bind_dst_ep), eui64=norm))
            st.success(f"Sent bind_set (id={cid})")

# 3. Network Tab
with tab_net:
    n_col1, n_col2, n_col3, n_col4 = st.columns(4)
    pan = n_col1.text_input("PAN ID", "0xbeef")
    ch = n_col2.number_input("Channel", 11, 26, 11)
    pwr = n_col3.number_input("TX Power", -30, 20, 20)
    force = n_col4.checkbox("Force Re-form")
    
    bn1, bn2 = st.columns(2)
    if bn1.button("Form Network", use_container_width=True, disabled=not rt["connected"]):
        cid = next_cmd_id()
        send_cmd_line(make_cmd("net_form", cid, pan_id=pan, ch=int(ch), tx_power=int(pwr), force=(1 if force else 0)))
        st.success(f"Sent net_form (id={cid})")
        
    if bn2.button("Save Config", use_container_width=True, disabled=not rt["connected"]):
        cid = next_cmd_id()
        send_cmd_line(make_cmd("net_cfg_set", cid, pan_id=pan, ch=int(ch), tx_power=int(pwr)))
        st.success(f"Sent net_cfg_set (id={cid})")

# 4. Device Tab
with tab_dev:
    d_col1, d_col2 = st.columns(2)
    with d_col1:
        if st.button("Request @INFO", use_container_width=True, disabled=not rt["connected"]):
            cid = next_cmd_id()
            send_cmd_line(make_cmd("info", cid))
            st.success("Sent Info Request")
    with d_col2:
        c_th_col, c_btn_col = st.columns([2,1])
        close_th = c_th_col.number_input("Auto-Close Threshold", 0, 65535, 60)
        if c_btn_col.button("Set TH", use_container_width=True, disabled=not rt["connected"]):
            cid = next_cmd_id()
            send_cmd_line(make_cmd("threshold_set", cid, close_th=int(close_th)))
            st.success("Sent Threshold Set")

st.divider()

# --- BOTTOM SECTION: LOGS & DEBUG ---
st.subheader("📝 Response Inspector")

r1, r2, r3 = st.columns(3)
with r1:
    with st.container(border=True):
        st.markdown("**Latest @ACK**")
        if last_ack:
            st.json(last_ack, expanded=False)
            st.caption(f"Time: {rt.get('last_ack_ts').strftime('%H:%M:%S')}")
        else:
            st.caption("No data")

with r2:
    with st.container(border=True):
        st.markdown("**Latest @INFO**")
        if last_info:
            st.json(last_info, expanded=False)
            st.caption(f"Time: {rt.get('last_info_ts').strftime('%H:%M:%S')}")
        else:
            st.caption("No data")

with r3:
    with st.container(border=True):
        st.markdown("**Latest @LOG**")
        if last_log:
            st.json(last_log, expanded=False)
            st.caption(f"Time: {rt.get('last_log_ts').strftime('%H:%M:%S')}")
        else:
            st.caption("No data")

# Raw Data Tables
if show_table and latest is not None:
    with st.expander("📂 Raw Telemetry History", expanded=False):
        st.dataframe(df.tail(30), use_container_width=True)

if show_log:
    with st.expander("📜 Terminal Log (RX)", expanded=False):
        st.code("\n".join(log_copy[:200]) if log_copy else "(empty)", language="text")