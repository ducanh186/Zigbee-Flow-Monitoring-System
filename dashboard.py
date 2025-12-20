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


# -----------------------------
# Helpers
# -----------------------------
def list_serial_ports():
    return [(p.device, p.description) for p in list_ports.comports()]


def _parse_prefixed_json(line: str, prefix: str):
    """
    Parse lines like:
      @DATA {...}
      @ACK  {...}
      @INFO {...}
    Return dict or None
    """
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
    """
    Build one command line to send to coordinator.
    Must end with '\n'.
    """
    payload = {"id": cmd_id, "op": op}
    payload.update(kwargs)
    return "@CMD " + json.dumps(payload) + "\n"


def normalize_eui64(s: str):
    """
    Extract only hex characters from input and validate it's exactly 16 hex digits.
    Returns uppercase normalized EUI64 or None if invalid.
    """
    hex_only = re.sub(r"[^0-9a-fA-F]", "", s or "")
    if len(hex_only) != 16:
        return None
    return hex_only.upper()


def reader_thread_fn(port, baud, stop_event, tx_queue: Queue,
                     data_buf: deque, rx_log: deque, state_dict: dict, lock: threading.Lock):
    """
    Background thread: open UART, read lines, parse @DATA/@ACK/@INFO/@LOG.
    Also drains tx_queue to send commands.
    """
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
            # 1) TX: drain queue (non-blocking)
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

            # 2) RX: read one line
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


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Zigbee Flow Dashboard (UART Gateway)", layout="wide")
st.title("Zigbee Flow Monitoring — UART Gateway Dashboard")

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


def next_cmd_id():
    st.session_state.cmd_id += 1
    return st.session_state.cmd_id


def send_cmd_line(line: str):
    st.session_state.tx_queue.put(line)


# Sidebar controls
st.sidebar.header("Connection")
ports = list_serial_ports()
port_options = [p[0] for p in ports] if ports else []
port_labels = {p[0]: f"{p[0]} — {p[1]}" for p in ports}

default_port_idx = 0
if "COM7" in port_options:
    default_port_idx = port_options.index("COM7")

selected_port = st.sidebar.selectbox(
    "Serial Port",
    options=port_options,
    index=default_port_idx if port_options else 0,
    format_func=lambda x: port_labels.get(x, x),
    disabled=st.session_state.rt_state["connected"],
)

baud = st.sidebar.number_input(
    "Baudrate",
    min_value=1200,
    max_value=2000000,
    value=38400,
    step=1200,
    disabled=st.session_state.rt_state["connected"],
)

col_a, col_b = st.sidebar.columns(2)
connect = col_a.button("Connect", disabled=st.session_state.rt_state["connected"])
disconnect = col_b.button("Disconnect", disabled=not st.session_state.rt_state["connected"])

auto_refresh_ms = st.sidebar.slider("Auto-refresh (ms)", 200, 3000, 800, 100)
show_table = st.sidebar.checkbox("Show raw table", value=True)
show_log = st.sidebar.checkbox("Show raw RX log", value=True)

# Connect/disconnect logic
if connect:
    if not selected_port:
        st.sidebar.error("No serial port selected.")
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
                selected_port,
                int(baud),
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

if disconnect:
    st.session_state.stop_event.set()
    time.sleep(0.2)
    with st.session_state.lock:
        st.session_state.rt_state["connected"] = False
    st.rerun()

# Read state snapshot
with st.session_state.lock:
    rt = dict(st.session_state.rt_state)
    data_copy = list(st.session_state.data_buf)
    log_copy = list(st.session_state.rx_log)
    last_ack = rt.get("last_ack")
    last_info = rt.get("last_info")
    last_log = rt.get("last_log")

# Latest valve state from telemetry
valve_state = None
if data_copy:
    valve_state = str(data_copy[-1].get("valve", "")).lower() or None

# Auto refresh
if rt["connected"]:
    st_autorefresh(interval=auto_refresh_ms, key="datarefresh")

# Status bar
c1, c2, c3, c4 = st.columns([1.2, 1.3, 1.3, 2.2])
c1.write(f"**Status:** {'🟢 Connected' if rt['connected'] else '🔴 Disconnected'}")
c2.write(f"**RX lines:** {rt.get('lines_total',0)} | **TX cmd:** {rt.get('tx_total',0)}")
c3.write(f"**DATA:** {rt.get('data_total',0)} | **ACK:** {rt.get('ack_total',0)} | **INFO:** {rt.get('info_total',0)} | **LOG:** {rt.get('log_total',0)}")
err = rt.get("last_error", "")
if err:
    c4.error(err)
else:
    c4.write(
        f"**Last DATA:** {rt.get('last_data_ts').strftime('%H:%M:%S') if rt.get('last_data_ts') else '-'} | "
        f"**Last ACK:** {rt.get('last_ack_ts').strftime('%H:%M:%S') if rt.get('last_ack_ts') else '-'} | "
        f"**Last INFO:** {rt.get('last_info_ts').strftime('%H:%M:%S') if rt.get('last_info_ts') else '-'}"
    )

st.divider()

# -----------------------------
# Control panel (TX)
# -----------------------------
st.subheader("Controls (TX -> Coordinator)")

ctrl1, ctrl2, ctrl3 = st.columns([1.1, 1.6, 1.3])

with ctrl1:
    st.markdown("### Valve control")

    if valve_state == "open":
        st.success("Valve status: OPEN", icon="🟢")
    elif valve_state == "closed":
        st.error("Valve status: CLOSED", icon="🔴")
    else:
        st.info("Valve status: Unknown", icon="ℹ️")

    b_open = st.button(
        "🟢 Open valve",
        use_container_width=True,
        disabled=not rt["connected"],
        type="primary" if valve_state == "open" else "secondary",
    )
    b_close = st.button(
        "🔴 Close valve",
        use_container_width=True,
        disabled=not rt["connected"],
        type="primary" if valve_state == "closed" else "secondary",
    )

    if b_open:
        cid = next_cmd_id()
        send_cmd_line(make_cmd("valve_set", cid, value="open"))
        st.success(f"Sent valve_set open (id={cid})")

    if b_close:
        cid = next_cmd_id()
        send_cmd_line(make_cmd("valve_set", cid, value="closed"))
        st.success(f"Sent valve_set closed (id={cid})")

with ctrl2:
    st.markdown("### Binding Setup (Coordinator -> Valve)")
    st.caption("Configure binding table for valve control via On/Off cluster")
    
    bind_index = st.number_input("Binding index", min_value=0, max_value=15, value=0, step=1, disabled=not rt["connected"])
    bind_cluster = st.text_input("Cluster (hex)", value="0x0006", disabled=not rt["connected"])
    bind_src_ep = st.number_input("Source EP (coord)", min_value=1, max_value=240, value=2, step=1, disabled=not rt["connected"])
    bind_dst_ep = st.number_input("Dest EP (valve)", min_value=1, max_value=240, value=1, step=1, disabled=not rt["connected"])
    valve_eui64 = st.text_input("Valve EUI64 (16 hex)", value="", disabled=not rt["connected"], 
                                 placeholder="000D6F0000AABBCC",
                                 help="Get this from Valve node's @INFO or 'info' CLI command")
    
    b_bind = st.button("Set Binding", use_container_width=True, disabled=not rt["connected"])
    if b_bind:
        norm = normalize_eui64(valve_eui64)
        if not norm:
            st.error("Valve EUI64 phải đúng 16 ký tự hex (vd: 000D6F0000AABBCC). Hãy paste từ 'info' của valve.")
        else:
            cid = next_cmd_id()
            send_cmd_line(make_cmd(
                "bind_set",
                cid,
                index=int(bind_index),
                cluster=str(bind_cluster),
                src_ep=int(bind_src_ep),
                dst_ep=int(bind_dst_ep),
                eui64=norm
            ))
            st.success(f"Sent bind_set (id={cid}, idx={bind_index}, eui64={norm})")

with ctrl3:
    st.markdown("### Form Network")
    pan = st.text_input("PAN ID (hex)", value="0xbeef", disabled=not rt["connected"])
    ch = st.number_input("Channel", min_value=11, max_value=26, value=11, step=1, disabled=not rt["connected"])
    pwr = st.number_input("TX Power (dBm)", min_value=-30, max_value=20, value=20, step=1, disabled=not rt["connected"])
    force = st.checkbox("Force re-form (leave then form)", value=False, disabled=not rt["connected"])
    
    b_form = st.button("Form network", use_container_width=True, disabled=not rt["connected"])
    if b_form:
        cid = next_cmd_id()
        send_cmd_line(make_cmd("net_form", cid, pan_id=pan, ch=int(ch), tx_power=int(pwr), force=(1 if force else 0)))
        st.success(f"Sent net_form (id={cid}, force={1 if force else 0})")
    
    b_cfg_set = st.button("Save as default config", use_container_width=True, disabled=not rt["connected"])
    if b_cfg_set:
        cid = next_cmd_id()
        send_cmd_line(make_cmd("net_cfg_set", cid, pan_id=pan, ch=int(ch), tx_power=int(pwr)))
        st.success(f"Sent net_cfg_set (id={cid})")

    st.markdown("### Info / Threshold")
    b_info = st.button("Request @INFO", use_container_width=True, disabled=not rt["connected"])
    if b_info:
        cid = next_cmd_id()
        send_cmd_line(make_cmd("info", cid))
        st.success(f"Sent info (id={cid})")

    close_th = st.number_input("Auto close threshold (flow > TH => close)", min_value=0, max_value=65535, value=60, step=1, disabled=not rt["connected"])
    b_th = st.button("Set threshold", use_container_width=True, disabled=not rt["connected"])
    if b_th:
        cid = next_cmd_id()
        send_cmd_line(make_cmd("threshold_set", cid, close_th=int(close_th)))
        st.success(f"Sent threshold_set (id={cid})")

st.divider()

# -----------------------------
# Latest ACK/INFO/LOG display
# -----------------------------
a1, a2, a3 = st.columns(3)

with a1:
    st.subheader("Latest @ACK")
    if last_ack:
        st.json(last_ack)
    else:
        st.info("No @ACK yet.")

with a2:
    st.subheader("Latest @INFO")
    if last_info:
        st.json(last_info)
    else:
        st.info("No @INFO yet.")

with a3:
    st.subheader("Latest @LOG")
    if last_log:
        st.json(last_log)
    else:
        st.info("No @LOG yet.")

st.divider()

# -----------------------------
# DATA display
# -----------------------------
st.subheader("Telemetry (@DATA)")

if not data_copy:
    st.warning("No @DATA received yet. Sensor may not be reporting, or parsing is not seeing @DATA lines.")
else:
    df = pd.DataFrame(data_copy)
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.sort_values("ts")

    latest = df.iloc[-1]
    m1, m2, m3 = st.columns(3)
    m1.metric("Flow", f"{int(latest['flow'])}")
    m2.metric("Battery", f"{int(latest['battery'])}%")
    m3.metric("Valve", str(latest["valve"]))

    st.subheader("Flow (live)")
    st.line_chart(df.set_index("ts")[["flow"]])

    st.subheader("Battery (live)")
    st.line_chart(df.set_index("ts")[["battery"]])

    if show_table:
        st.subheader("Latest samples")
        st.dataframe(df.tail(30), use_container_width=True)

if show_log:
    with st.expander("Raw RX log (latest first)"):
        st.code("\n".join(log_copy[:200]) if log_copy else "(empty)")
