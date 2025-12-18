import json
import threading
import time
from collections import deque
from datetime import datetime

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


def parse_data_line(line: str):
    """
    Accept lines like:
      @DATA {"flow":120,"battery":90,"valve":"open"}
    Ignore everything else.
    """
    if not line:
        return None

    s = line.strip()
    if not s:
        return None

    # case-insensitive prefix
    if not s.upper().startswith("@DATA "):
        return None

    payload = s[6:].strip()
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None

    # normalize fields
    flow = int(obj.get("flow", 0))
    battery = int(obj.get("battery", 0))
    valve = str(obj.get("valve", "unknown")).lower()

    # optional normalization: close -> closed
    if valve == "close":
        valve = "closed"

    return {
        "ts": datetime.now(),
        "flow": flow,
        "battery": battery,
        "valve": valve,
    }


def reader_thread_fn(port, baud, stop_event, buffer_deque, state_dict, lock):
    """
    Background thread: read UART, parse @DATA, push to buffer.
    """
    ser = None
    try:
        ser = serial.Serial(port=port, baudrate=baud, timeout=1)
        with lock:
            state_dict["connected"] = True
            state_dict["last_error"] = ""
            state_dict["connected_since"] = datetime.now()
            state_dict["lines_total"] = 0
            state_dict["data_total"] = 0

        while not stop_event.is_set():
            raw = ser.readline()
            if not raw:
                continue

            try:
                line = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue

            with lock:
                state_dict["lines_total"] += 1

            rec = parse_data_line(line)
            if rec is None:
                continue

            with lock:
                buffer_deque.append(rec)
                state_dict["data_total"] += 1
                state_dict["last_data_ts"] = rec["ts"]

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
st.set_page_config(page_title="Zigbee Flow Dashboard (Simple)", layout="wide")
st.title("Zigbee Flow Monitoring — Simple Dashboard")

# Session state init
if "buf" not in st.session_state:
    st.session_state.buf = deque(maxlen=600)  # keep last ~600 samples
if "stop_event" not in st.session_state:
    st.session_state.stop_event = threading.Event()
if "thread" not in st.session_state:
    st.session_state.thread = None
if "lock" not in st.session_state:
    st.session_state.lock = threading.Lock()
if "rt_state" not in st.session_state:
    st.session_state.rt_state = {
        "connected": False,
        "connected_since": None,
        "last_data_ts": None,
        "lines_total": 0,
        "data_total": 0,
        "last_error": "",
    }

# Sidebar controls
st.sidebar.header("Connection")
ports = list_serial_ports()
port_options = [p[0] for p in ports] if ports else []
port_labels = {p[0]: f"{p[0]} — {p[1]}" for p in ports}

# Default to COM7 if available
default_port_idx = 0
if "COM7" in port_options:
    default_port_idx = port_options.index("COM7")

selected_port = st.sidebar.selectbox(
    "Serial Port",
    options=port_options,
    index=default_port_idx,
    format_func=lambda x: port_labels.get(x, x),
    disabled=st.session_state.rt_state["connected"],
)

baud = st.sidebar.number_input(
    "Baudrate",
    min_value=1200,
    max_value=2000000,
    value=9600,  # Changed from 115200 to 9600
    step=1200,
    disabled=st.session_state.rt_state["connected"],
)

col_a, col_b = st.sidebar.columns(2)
connect = col_a.button("Connect", disabled=st.session_state.rt_state["connected"])
disconnect = col_b.button("Disconnect", disabled=not st.session_state.rt_state["connected"])

auto_refresh_ms = st.sidebar.slider("Auto-refresh (ms)", 200, 3000, 800, 100)
show_table = st.sidebar.checkbox("Show raw table", value=True)

# Connect/disconnect logic
if connect:
    if not selected_port:
        st.sidebar.error("No serial port selected.")
    else:
        # Stop any existing thread first
        if st.session_state.thread is not None and st.session_state.thread.is_alive():
            st.session_state.stop_event.set()
            st.session_state.thread.join(timeout=1)
        
        st.session_state.stop_event.clear()
        st.session_state.buf.clear()  # Clear old data
        t = threading.Thread(
            target=reader_thread_fn,
            args=(
                selected_port,
                int(baud),
                st.session_state.stop_event,
                st.session_state.buf,
                st.session_state.rt_state,
                st.session_state.lock,
            ),
            daemon=True,
        )
        st.session_state.thread = t
        t.start()
        time.sleep(0.3)
        st.rerun()

if disconnect:
    st.session_state.stop_event.set()
    time.sleep(0.3)
    with st.session_state.lock:
        st.session_state.rt_state["connected"] = False
    st.rerun()

# Read state (must be before auto-refresh check)
with st.session_state.lock:
    rt = dict(st.session_state.rt_state)
    buf_copy = list(st.session_state.buf)

# Auto refresh - use streamlit-autorefresh (no JavaScript reload!)
if rt["connected"]:
    st_autorefresh(interval=auto_refresh_ms, key="datarefresh")

# Status

status_col1, status_col2, status_col3 = st.columns([1.2, 1, 1.8])
status_col1.write(
    f"**Status:** {'🟢 Connected' if rt['connected'] else '🔴 Disconnected'}"
)
status_col2.write(f"**Lines RX:** {rt.get('lines_total', 0)} | **DATA RX:** {rt.get('data_total', 0)}")
last_err = rt.get("last_error", "")
if last_err:
    status_col3.error(f"Reader error: {last_err}")
else:
    status_col3.write(
        f"**Last DATA:** {rt.get('last_data_ts').strftime('%H:%M:%S') if rt.get('last_data_ts') else '-'}"
    )

# Main metrics + chart
if not buf_copy:
    st.warning("No @DATA received yet. Make sure Coordinator is sending lines like: @DATA {...}")
    st.stop()

df = pd.DataFrame(buf_copy)
df["ts"] = pd.to_datetime(df["ts"])
df = df.sort_values("ts")

latest = df.iloc[-1]
m1, m2, m3 = st.columns(3)
m1.metric("Flow", f"{int(latest['flow'])}")
m2.metric("Battery", f"{int(latest['battery'])}%")
m3.metric("Valve", str(latest["valve"]))

st.subheader("Flow (live)")
flow_df = df.set_index("ts")[["flow"]]
st.line_chart(flow_df)

st.subheader("Battery (live)")
batt_df = df.set_index("ts")[["battery"]]
st.line_chart(batt_df)

if show_table:
    st.subheader("Latest samples")
    # show last 30 rows
    st.dataframe(df.tail(30), use_container_width=True)
