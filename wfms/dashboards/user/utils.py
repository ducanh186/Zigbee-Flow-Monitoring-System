import os
import time
from datetime import datetime
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

# =============================================================================
# Load .env
# =============================================================================
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if not ENV_PATH.exists():
    from pathlib import Path
    # Try finding it relative to cwd if run from root
    cwd_env = Path(".env").resolve()
    if cwd_env.exists():
        ENV_PATH = cwd_env

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

# =============================================================================
# Configuration
# =============================================================================
MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
SITE = os.getenv("SITE", "lab1")

# Buffer sizes
TELEMETRY_BUFFER_SIZE = 500
ACK_BUFFER_SIZE = 200
FLOW_HISTORY_SIZE = 500
CMD_BUFFER_SIZE = 100

# =============================================================================
# Utility Functions
# =============================================================================
def format_time_short(ts):
    if ts is None:
        return "--"
    try:
        return datetime.fromtimestamp(ts).strftime('%H:%M:%S')
    except:
        return str(ts)

def format_ago(ts):
    if ts is None:
        return "--"
    try:
        diff = int(time.time() - ts)
        if diff < 60:
            return f"{diff}s ago"
        elif diff < 3600:
            return f"{diff // 60}m ago"
        elif diff < 86400:
            return f"{diff // 3600}h ago"
        else:
            return f"{diff // 86400}d ago"
    except:
        return "--"

def add_log(message: str, log_type: str = "info"):
    """Add a log entry to session state"""
    if "logs" not in st.session_state:
        st.session_state.logs = []
    
    log_entry = {
        "time": datetime.now().strftime('%H:%M:%S'),
        "message": message,
        "type": log_type
    }
    st.session_state.logs.insert(0, log_entry)
    # Keep only last 50 logs
    st.session_state.logs = st.session_state.logs[:50]

# =============================================================================
# Session State Initialization
# =============================================================================
def init_session_state():
    if "current_mode" not in st.session_state:
        st.session_state.current_mode = "AUTO"
    if "logs" not in st.session_state:
        st.session_state.logs = [
            {"time": datetime.now().strftime('%H:%M:%S'), "message": "System initialized", "type": "success"},
            {"time": datetime.now().strftime('%H:%M:%S'), "message": "Connected to MQTT Broker", "type": "success"},
            {"time": datetime.now().strftime('%H:%M:%S'), "message": f"Subscribed to wfms/{SITE}/telemetry", "type": "info"},
        ]
    if "time_window" not in st.session_state:
        st.session_state.time_window = "Live"
