import os
import time
import json
import threading
import uuid
import pathlib
import requests
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

# =============================================================================
# CONFIGURATION
# =============================================================================

ENV_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / ".env"
if not ENV_PATH.exists():
    from pathlib import Path
    # Try finding it relative to cwd if run from root
    cwd_env = Path(".env").resolve()
    if cwd_env.exists():
        ENV_PATH = cwd_env
        
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

# Read from .env - no hardcoded defaults for critical settings
DEFAULT_CONFIG = {
    "api_base_url": f"http://localhost:{os.getenv('API_PORT', '8080')}",
    "mqtt_host": os.getenv("MQTT_HOST"),  # Required from .env
    "mqtt_port": int(os.getenv("MQTT_PORT", "1883")),
    "mqtt_user": os.getenv("MQTT_USER", ""),
    "mqtt_pass": os.getenv("MQTT_PASS", ""),
    "site": os.getenv("SITE", "lab1"),
    "uart_port": os.getenv("UART_PORT", "COM7"),
    "uart_baud": int(os.getenv("UART_BAUD", "115200")),
}

# =============================================================================
# STATE MANAGEMENT
# =============================================================================

def init_session_state():
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Live View"
    if "config" not in st.session_state:
        st.session_state.config = DEFAULT_CONFIG.copy()
    if "config_applied_at" not in st.session_state:
        st.session_state.config_applied_at = None
    if "logs_data" not in st.session_state:
        st.session_state.logs_data = None
    if "logs_error" not in st.session_state:
        st.session_state.logs_error = None
    if "current_mode" not in st.session_state:
        st.session_state.current_mode = "AUTO"
    if "logs" not in st.session_state:
        st.session_state.logs = [
            {"time": datetime.now().strftime('%H:%M:%S'), "message": "Admin Dashboard initialized", "type": "success"},
            {"time": datetime.now().strftime('%H:%M:%S'), "message": "Connecting to MQTT Broker...", "type": "info"},
        ]
    if "time_window" not in st.session_state:
        st.session_state.time_window = "Live"


def get_config():
    if "config" not in st.session_state:
        st.session_state.config = DEFAULT_CONFIG.copy()
    return st.session_state.config


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
    st.session_state.logs = st.session_state.logs[:100]


# =============================================================================
# HTTP API HELPERS
# =============================================================================

def api_get(endpoint: str, timeout: int = 5):
    try:
        config = get_config()
        url = f"{config['api_base_url']}{endpoint}"
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return True, response.json(), None
    except requests.exceptions.Timeout:
        return False, None, f"Timeout after {timeout}s"
    except requests.exceptions.ConnectionError:
        return False, None, "Cannot connect to API"
    except requests.exceptions.HTTPError as e:
        return False, None, f"HTTP {e.response.status_code}"
    except json.JSONDecodeError:
        return False, None, "Invalid JSON"
    except Exception as e:
        return False, None, str(e)


def api_post(endpoint: str, payload, timeout: int = 5):
    try:
        config = get_config()
        url = f"{config['api_base_url']}{endpoint}"
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return True, response.json(), None
    except requests.exceptions.Timeout:
        return False, None, f"Timeout after {timeout}s"
    except requests.exceptions.ConnectionError:
        return False, None, "Cannot connect to API"
    except requests.exceptions.HTTPError as e:
        return False, None, f"HTTP {e.response.status_code}"
    except json.JSONDecodeError:
        return False, None, "Invalid JSON"
    except Exception as e:
        return False, None, str(e)


# =============================================================================
# FORMATTING UTILS
# =============================================================================

def format_timestamp(ts):
    if ts is None:
        return "--"
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return str(ts)


def format_time_short(ts):
    if ts is None:
        return "--"
    try:
        return datetime.fromtimestamp(ts).strftime('%H:%M:%S')
    except:
        return str(ts)


def format_uptime(seconds):
    if seconds is None:
        return "--"
    try:
        seconds = int(seconds)
        d, r = divmod(seconds, 86400)
        h, r = divmod(r, 3600)
        m, s = divmod(r, 60)
        parts = []
        if d: parts.append(f"{d}d")
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        parts.append(f"{s}s")
        return " ".join(parts)
    except:
        return str(seconds)


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
