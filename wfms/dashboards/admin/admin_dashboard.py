"""
WFMS Admin Dashboard - Streamlit Application
=============================================
A production-ready admin dashboard for the Water Flow Monitoring System.

Dependencies:
    pip install streamlit streamlit-option-menu requests paho-mqtt python-dotenv plotly pandas streamlit-autorefresh

Run:
    streamlit run admin_dashboard.py

Default Configuration:
    API_BASE_URL: http://localhost:8080
    MQTT_HOST: from .env or 127.0.0.1
    MQTT_PORT: 1883
    SITE: lab1
"""

import streamlit as st
import requests
import paho.mqtt.client as mqtt
import json
import time
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
from dotenv import load_dotenv
import pathlib
import pandas as pd

# Optional imports with fallback
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    from streamlit_option_menu import option_menu
    OPTION_MENU_AVAILABLE = True
except ImportError:
    OPTION_MENU_AVAILABLE = False

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

# =============================================================================
# CONFIGURATION
# =============================================================================

ENV_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / ".env"
if not ENV_PATH.exists():
    raise FileNotFoundError(f"Configuration file not found: {ENV_PATH}")
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

# Validate required settings
if not DEFAULT_CONFIG["mqtt_host"]:
    raise ValueError("MQTT_HOST must be set in .env file")

TELEMETRY_BUFFER_SIZE = 500
ACK_BUFFER_SIZE = 200
FLOW_HISTORY_SIZE = 500
CMD_BUFFER_SIZE = 100


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


def get_config() -> Dict:
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

def api_get(endpoint: str, timeout: int = 5) -> Tuple[bool, Optional[Dict], Optional[str]]:
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


def api_post(endpoint: str, payload: Dict, timeout: int = 5) -> Tuple[bool, Optional[Dict], Optional[str]]:
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
# MQTT CLIENT MANAGER
# =============================================================================

class MQTTManager:
    def __init__(self, config: Dict):
        self._config = config.copy()
        self.connected = False
        self.last_error = None
        self.last_message_time = None
        self.parse_error_count = 0
        self.reconnect_count = 0
        self.connect_time = None
        
        self.latest_state = {}
        self.gateway_status = {}
        self.telemetry_buffer = deque(maxlen=TELEMETRY_BUFFER_SIZE)
        self.ack_buffer = deque(maxlen=ACK_BUFFER_SIZE)
        self.flow_history = deque(maxlen=FLOW_HISTORY_SIZE)
        self.cmd_buffer = deque(maxlen=CMD_BUFFER_SIZE)
        
        self._lock = threading.Lock()
        self._running = False
        self.client = None
        
    def start(self):
        if self._running:
            return
        try:
            client_id = f"wfms_admin_{uuid.uuid4().hex[:8]}"
            self.client = mqtt.Client(client_id=client_id)
            
            if self._config.get("mqtt_user") and self._config.get("mqtt_pass"):
                self.client.username_pw_set(self._config["mqtt_user"], self._config["mqtt_pass"])
            
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            self.client.connect_async(self._config["mqtt_host"], self._config["mqtt_port"], keepalive=60)
            self.client.loop_start()
            self._running = True
        except Exception as e:
            self.last_error = f"Connection failed: {e}"
            self.connected = False
    
    def stop(self):
        self._running = False
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except:
                pass
        self.connected = False
    
    def reconnect(self, new_config: Dict):
        self.stop()
        time.sleep(0.5)
        self._config = new_config.copy()
        self.reconnect_count += 1
        self.start()
    
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            self.last_error = None
            self.connect_time = time.time()
            site = self._config["site"]
            client.subscribe([
                (f"wfms/{site}/state", 1),
                (f"wfms/{site}/telemetry", 0),
                (f"wfms/{site}/ack", 1),
                (f"wfms/{site}/status/gateway", 1),
            ])
        else:
            self.connected = False
            self.last_error = f"Connection refused (rc={rc})"
    
    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            self.last_error = f"Disconnected (rc={rc})"
    
    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode('utf-8'))
            with self._lock:
                self.last_message_time = time.time()
                site = self._config["site"]
                
                if msg.topic == f"wfms/{site}/state":
                    self.latest_state = data
                    if 'mode' in data:
                        import streamlit as st
                        if 'current_mode' in st.session_state:
                            st.session_state.current_mode = data['mode']
                    if 'flow' in data:
                        self.flow_history.append({
                            'ts': data.get('ts', data.get('updatedAt', time.time())),
                            'flow': data['flow'],
                            'received_at': time.time()
                        })
                elif msg.topic == f"wfms/{site}/telemetry":
                    data['received_at'] = time.time()
                    self.telemetry_buffer.appendleft(data)
                    if 'flow' in data:
                        self.flow_history.append({
                            'ts': data.get('ts', time.time()),
                            'flow': data['flow'],
                            'received_at': time.time()
                        })
                elif msg.topic == f"wfms/{site}/ack":
                    data['received_at'] = time.time()
                    self.ack_buffer.appendleft(data)
                elif msg.topic == f"wfms/{site}/status/gateway":
                    self.gateway_status = data
        except json.JSONDecodeError:
            with self._lock:
                self.parse_error_count += 1
        except:
            pass
    
    def get_state(self):
        with self._lock:
            return self.latest_state.copy()
    
    def get_gateway_status(self):
        with self._lock:
            return self.gateway_status.copy()
    
    def get_telemetry(self, limit=20):
        with self._lock:
            return list(self.telemetry_buffer)[:limit]
    
    def get_acks(self, limit=20):
        with self._lock:
            return list(self.ack_buffer)[:limit]
    
    def get_flow_history(self, limit=200):
        with self._lock:
            return list(self.flow_history)[-limit:]
    
    def get_commands(self, limit=20):
        with self._lock:
            return list(self.cmd_buffer)[:limit]
    
    def publish(self, topic: str, payload: Dict) -> Tuple[bool, Optional[str]]:
        """Publish a message to MQTT broker"""
        if not self.connected or not self.client:
            return False, "Not connected to MQTT broker"
        try:
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                with self._lock:
                    cmd_record = payload.copy()
                    cmd_record['sent_at'] = time.time()
                    cmd_record['topic'] = topic
                    self.cmd_buffer.appendleft(cmd_record)
                return True, None
            else:
                return False, f"Publish failed (rc={result.rc})"
        except Exception as e:
            return False, str(e)
    
    def get_stats(self):
        with self._lock:
            return {
                'connected': self.connected,
                'last_error': self.last_error,
                'last_message_time': self.last_message_time,
                'parse_error_count': self.parse_error_count,
                'telemetry_count': len(self.telemetry_buffer),
                'ack_count': len(self.ack_buffer),
                'cmd_count': len(self.cmd_buffer),
                'reconnect_count': self.reconnect_count,
                'connect_time': self.connect_time,
                'mqtt_host': self._config.get('mqtt_host'),
                'mqtt_port': self._config.get('mqtt_port'),
            }


def get_mqtt_manager():
    config = get_config()
    if 'mqtt_manager' not in st.session_state:
        st.session_state.mqtt_manager = MQTTManager(config)
        st.session_state.mqtt_manager.start()
    return st.session_state.mqtt_manager


def reconnect_mqtt():
    config = get_config()
    if 'mqtt_manager' in st.session_state:
        st.session_state.mqtt_manager.reconnect(config)


# =============================================================================
# UTILITY FUNCTIONS
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


# =============================================================================
# CUSTOM CSS - Modern Dark Theme (matching user dashboard)
# =============================================================================

def inject_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
        
        /* Hide Streamlit defaults */
        #MainMenu, footer, header {visibility: hidden;}
        .block-container { padding: 1rem 1rem 0 1rem !important; max-width: 100% !important; }
        
        /* Base styling */
        .stApp { 
            background-color: #0E1117; 
            font-family: 'Inter', sans-serif;
        }
        
        /* Header bar styling */
        .header-bar {
            background: #262730;
            border-radius: 12px;
            padding: 12px 24px;
            border: 1px solid rgba(255,255,255,0.08);
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .header-icon {
            background: rgba(255, 75, 75, 0.2);
            padding: 8px;
            border-radius: 8px;
        }
        .header-title {
            font-size: 18px;
            font-weight: 700;
            color: #FAFAFA;
            margin: 0;
        }
        .header-subtitle {
            font-size: 11px;
            color: #9CA3AF;
            font-family: 'JetBrains Mono', monospace;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .header-stats {
            display: flex;
            align-items: center;
            gap: 24px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
        }
        .status-online {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #00E676;
        }
        .status-offline {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #FF5252;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #00E676;
            animation: pulse 2s infinite;
        }
        .status-dot-off {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #FF5252;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .broker-info { color: #9CA3AF; }
        .broker-info span { color: #FAFAFA; }
        .packet-badge {
            background: rgba(0,0,0,0.3);
            padding: 4px 12px;
            border-radius: 6px;
            border: 1px solid #374151;
        }
        
        /* Panel styling */
        .glass-panel {
            background: rgba(38, 39, 48, 0.9);
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
            padding: 16px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        
        /* Valve status card */
        .valve-card {
            background: #262730;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
            padding: 20px;
            position: relative;
            overflow: hidden;
        }
        .valve-glow-open {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: #00E676;
            box-shadow: 0 0 20px rgba(0,230,118,0.5);
        }
        .valve-glow-closed {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: #FF5252;
            box-shadow: 0 0 20px rgba(255,82,82,0.5);
        }
        .valve-icon-open {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: rgba(0,230,118,0.1);
            border: 2px solid rgba(0,230,118,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto;
            box-shadow: 0 0 30px rgba(0,230,118,0.2);
        }
        .valve-icon-closed {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: rgba(255,82,82,0.1);
            border: 2px solid rgba(255,82,82,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto;
            box-shadow: 0 0 30px rgba(255,82,82,0.2);
        }
        .valve-text-open {
            font-size: 28px;
            font-weight: 700;
            color: #00E676;
            text-align: center;
            margin-top: 8px;
            letter-spacing: 2px;
        }
        .valve-text-closed {
            font-size: 28px;
            font-weight: 700;
            color: #FF5252;
            text-align: center;
            margin-top: 8px;
            letter-spacing: 2px;
        }
        
        /* Metric boxes */
        .metric-box {
            background: rgba(0,0,0,0.2);
            border: 1px solid #374151;
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }
        .metric-label {
            font-size: 11px;
            color: #9CA3AF;
            margin-bottom: 4px;
        }
        .metric-value {
            font-size: 24px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            color: #29b5e8;
        }
        .metric-unit {
            font-size: 12px;
            color: #6B7280;
            font-weight: 400;
        }
        
        /* Lock overlay */
        .lock-overlay {
            background: rgba(38,39,48,0.9);
            backdrop-filter: blur(4px);
            border-radius: 12px;
            padding: 24px;
            text-align: center;
            border: 1px solid #374151;
        }
        
        /* Log panel */
        .log-panel {
            background: #262730;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
            padding: 12px;
            height: 140px;
            overflow-y: auto;
        }
        .log-entry {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            padding: 2px 4px;
            border-radius: 2px;
        }
        .log-entry:hover {
            background: rgba(255,255,255,0.05);
        }
        .log-time { color: #4B5563; }
        .log-info { color: #9CA3AF; }
        .log-success { color: #00E676; }
        .log-error { color: #FF5252; }
        .log-warn { color: #FFC107; }
        
        /* Gateway health */
        .gateway-panel {
            background: #262730;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
            padding: 16px;
        }
        
        /* Command history */
        .cmd-entry {
            background: rgba(0,0,0,0.2);
            border: 1px solid rgba(55,65,81,0.5);
            border-radius: 6px;
            padding: 8px 12px;
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .cmd-action {
            font-size: 12px;
            font-weight: 700;
            color: #FAFAFA;
        }
        .cmd-source {
            font-size: 10px;
            color: #6B7280;
        }
        .cmd-time {
            font-size: 10px;
            font-family: 'JetBrains Mono', monospace;
            color: #9CA3AF;
        }
        
        /* Section headers */
        .section-header {
            font-size: 11px;
            font-weight: 700;
            color: #9CA3AF;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 12px;
        }
        
        /* Chart container */
        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .chart-title {
            font-size: 14px;
            font-weight: 600;
            color: #9CA3AF;
        }
        
        /* Buttons */
        .stButton > button {
            width: 100%;
            border-radius: 8px !important;
            font-weight: 700 !important;
            height: 50px !important;
            font-size: 15px !important;
        }
        
        /* Admin badge */
        .admin-badge {
            background: linear-gradient(135deg, #FF4B4B 0%, #FF6B6B 100%);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            margin-left: 8px;
        }
    </style>
    """, unsafe_allow_html=True)


# =============================================================================
# SIDEBAR
# =============================================================================

def render_sidebar():
    config = get_config()
    mqtt_mgr = get_mqtt_manager()
    stats = mqtt_mgr.get_stats()
    
    with st.sidebar:
        st.markdown("## 🚰 WFMS Admin")
        st.caption(f"Site: **{config['site']}**")
        st.divider()
        
        if OPTION_MENU_AVAILABLE:
            pages = ["Live View", "Network Setting", "System Logs"]
            icons = ["activity", "wifi", "file-text"]
            selected = option_menu(
                menu_title=None,
                options=pages,
                icons=icons,
                default_index=pages.index(st.session_state.current_page) if st.session_state.current_page in pages else 0,
                styles={
                    "container": {"padding": "0", "background-color": "#0e1117"},
                    "icon": {"color": "#FF4B4B", "font-size": "18px"},
                    "nav-link": {"font-size": "14px", "text-align": "left", "margin": "2px", "padding": "10px 15px"},
                    "nav-link-selected": {"background-color": "#1a1a2e", "border-left": "4px solid #FF4B4B"},
                }
            )
            st.session_state.current_page = selected
        else:
            st.subheader("📍 Navigation")
            for label, page in [("📊 Live View", "Live View"), 
                                ("🌐 Network Setting", "Network Setting"),
                                ("📋 System Logs", "System Logs")]:
                if st.session_state.current_page == page:
                    st.markdown(f"**→ {label}**")
                elif st.button(label, key=f"nav_{page}"):
                    st.session_state.current_page = page
                    st.rerun()
        
        st.divider()
        st.subheader("🔌 Connection Status")
        st.text(f"MQTT: {stats['mqtt_host']}:{stats['mqtt_port']}")
        
        if stats['connected']:
            st.success("✅ MQTT Connected")
        else:
            st.error(f"❌ {stats['last_error'] or 'Disconnected'}")
        
        if stats['last_message_time']:
            st.caption(f"Last: {format_ago(stats['last_message_time'])}")
        
        st.divider()
        auto_refresh = st.checkbox("🔄 Auto Refresh (2s)", key="auto_refresh")
        if auto_refresh:
            if AUTOREFRESH_AVAILABLE:
                st_autorefresh(interval=2000, key="refresh")
            else:
                time.sleep(2)
                st.rerun()
        
        if st.button("🔄 Refresh Now"):
            st.rerun()


# =============================================================================
# LIVE VIEW (Redesigned to match User Dashboard)
# =============================================================================

def render_live_view():
    mqtt_mgr = get_mqtt_manager()
    stats = mqtt_mgr.get_stats()
    state = mqtt_mgr.get_state()
    config = get_config()
    
    # Get current values
    is_connected = stats['connected']
    packet_count = len(mqtt_mgr.get_telemetry(500))
    
    # Parse valve state
    valve_state = "unknown"
    latest_flow = 0.0
    latest_battery = 0
    
    if state and isinstance(state, dict):
        valve_raw = state.get('valve', 'unknown')
        if isinstance(valve_raw, str):
            valve_state = valve_raw.lower()
            if valve_state in ['close', 'off']:
                valve_state = 'closed'
            elif valve_state in ['open', 'on']:
                valve_state = 'open'
        latest_flow = state.get('flow', 0) or 0
        latest_battery = state.get('battery', 0) or 0
    
    is_open = valve_state == 'open'
    
    # =========================================================================
    # HEADER BAR
    # =========================================================================
    status_class = "status-online" if is_connected else "status-offline"
    dot_class = "status-dot" if is_connected else "status-dot-off"
    status_text = "ONLINE" if is_connected else "OFFLINE"
    
    st.markdown(f"""
    <div class="header-bar">
        <div class="header-left">
            <div class="header-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FF4B4B" stroke-width="2">
                    <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>
                </svg>
            </div>
            <div>
                <h1 class="header-title">WFMS Admin Dashboard <span class="admin-badge">ADMIN</span></h1>
                <p class="header-subtitle">Site: {config['site'].upper()}</p>
            </div>
        </div>
        <div class="header-stats">
            <div class="{status_class}">
                <div class="{dot_class}"></div>
                <span>{status_text}</span>
            </div>
            <div class="broker-info">
                Broker: <span>{stats['mqtt_host']}</span>
            </div>
            <div class="packet-badge">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9CA3AF" stroke-width="2" style="display:inline;vertical-align:middle;margin-right:4px;">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                </svg>
                {packet_count:,} Pkts
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # =========================================================================
    # MAIN GRID: LEFT (2/3) + RIGHT (1/3)
    # =========================================================================
    col_left, col_right = st.columns([2, 1], gap="medium")
    
    # -------------------------------------------------------------------------
    # LEFT COLUMN: Chart + Logs
    # -------------------------------------------------------------------------
    with col_left:
        # FLOW CHART
        with st.container():
            st.markdown("""
            <div class="chart-header">
                <span class="chart-title">📈 Flow History</span>
            </div>
            """, unsafe_allow_html=True)
            
            # Time window selector
            tw_cols = st.columns([1, 1, 1, 6])
            with tw_cols[0]:
                if st.button("Live", key="tw_live", type="primary" if st.session_state.time_window == "Live" else "secondary"):
                    st.session_state.time_window = "Live"
            with tw_cols[1]:
                if st.button("15m", key="tw_15m", type="primary" if st.session_state.time_window == "15m" else "secondary"):
                    st.session_state.time_window = "15m"
            with tw_cols[2]:
                if st.button("1h", key="tw_1h", type="primary" if st.session_state.time_window == "1h" else "secondary"):
                    st.session_state.time_window = "1h"
            
            # Get flow data
            flow_data = mqtt_mgr.get_flow_history(200)
            
            if flow_data and len(flow_data) > 0 and PLOTLY_AVAILABLE:
                now = time.time()
                cutoff_map = {"Live": 120, "15m": 900, "1h": 3600}
                cutoff = now - cutoff_map.get(st.session_state.time_window, 120)
                filtered = [d for d in flow_data if d.get('received_at', d.get('ts', 0)) >= cutoff]
                
                if filtered:
                    df = pd.DataFrame(filtered)
                    if 'flow' in df.columns:
                        df['time'] = pd.to_datetime(df['received_at'].apply(datetime.fromtimestamp))
                        
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=df['time'], 
                            y=df['flow'],
                            mode='lines',
                            fill='tozeroy',
                            line=dict(color='#FF4B4B', width=2),
                            fillcolor='rgba(255, 75, 75, 0.3)',
                            name='Flow Rate'
                        ))
                        fig.update_layout(
                            height=220,
                            margin=dict(l=40, r=20, t=10, b=30),
                            paper_bgcolor='#262730',
                            plot_bgcolor='#262730',
                            xaxis=dict(showgrid=False, color='#888'),
                            yaxis=dict(gridcolor='#333', color='#888', title='L/min'),
                            showlegend=False,
                            hovermode='x unified'
                        )
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                    else:
                        st.info("Waiting for flow data...")
                else:
                    st.info("No data in selected window")
            else:
                st.info("📊 Waiting for telemetry data...")
        
        # BOTTOM: Logs + Gateway Health
        log_col, gw_col = st.columns([2, 1])
        
        with log_col:
            st.markdown('<p class="section-header">System Logs</p>', unsafe_allow_html=True)
            
            # Build log HTML
            log_html = '<div class="log-panel custom-scrollbar">'
            for log in st.session_state.get('logs', [])[:15]:
                color_class = f"log-{log['type']}"
                log_html += f'<div class="log-entry"><span class="log-time">{log["time"]}</span> <span class="{color_class}">{log["message"]}</span></div>'
            log_html += '</div>'
            st.markdown(log_html, unsafe_allow_html=True)
        
        with gw_col:
            st.markdown('<p class="section-header">Gateway Health</p>', unsafe_allow_html=True)
            
            gateway = mqtt_mgr.get_gateway_status()
            rssi = gateway.get('rssi', -42) if gateway else -42
            uptime = gateway.get('uptime', '4d 12h') if gateway else '4d 12h'
            signal_pct = min(100, max(0, (rssi + 100) * 2))
            
            st.markdown(f"""
            <div class="gateway-panel">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <span style="font-size:13px;color:#9CA3AF;">Signal (RSSI)</span>
                    <span style="font-family:'JetBrains Mono',monospace;color:#00E676;font-size:13px;">{rssi} dBm</span>
                </div>
                <div style="background:#374151;height:6px;border-radius:3px;overflow:hidden;margin-bottom:12px;">
                    <div style="background:#00E676;height:100%;width:{signal_pct}%;"></div>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:13px;color:#9CA3AF;">Uptime</span>
                    <span style="font-family:'JetBrains Mono',monospace;color:#FAFAFA;font-size:13px;">{uptime}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # -------------------------------------------------------------------------
    # RIGHT COLUMN: Status + Controls + History
    # -------------------------------------------------------------------------
    with col_right:
        # VALVE STATUS CARD
        glow_class = "valve-glow-open" if is_open else "valve-glow-closed"
        icon_class = "valve-icon-open" if is_open else "valve-icon-closed"
        text_class = "valve-text-open" if is_open else "valve-text-closed"
        valve_display = "OPEN" if is_open else "CLOSED"
        icon_color = "#00E676" if is_open else "#FF5252"
        
        valve_card_html = f'''<div class="valve-card">
            <div class="{glow_class}"></div>
            <p class="section-header" style="margin-bottom:16px;">VALVE STATUS</p>
            <div class="{icon_class}">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="{icon_color}" stroke-width="2">
                    <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>
                </svg>
            </div>
            <div class="{text_class}">{valve_display}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:20px;">
                <div class="metric-box">
                    <p class="metric-label">Flow Rate</p>
                    <p class="metric-value">{latest_flow:.1f} <span class="metric-unit">L/m</span></p>
                </div>
                <div class="metric-box">
                    <p class="metric-label">Battery</p>
                    <p class="metric-value" style="color:#FAFAFA;">{latest_battery} <span class="metric-unit">%</span></p>
                </div>
            </div>
        </div>'''
        st.markdown(valve_card_html, unsafe_allow_html=True)
        
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        
        # CONTROL PANEL
        st.markdown("""
        <div class="valve-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <span style="font-weight:700;font-size:15px;color:#FAFAFA;">🎮 Controls</span>
            </div>
        """, unsafe_allow_html=True)
        
        # Mode toggle
        current_mode = st.session_state.get('current_mode', 'AUTO')
        if state and isinstance(state, dict) and 'mode' in state:
            current_mode = state.get('mode', 'AUTO').upper()
            st.session_state.current_mode = current_mode
        
        mode_cols = st.columns(2)
        with mode_cols[0]:
            if st.button("🤖 AUTO", key="mode_auto", type="primary" if current_mode == "AUTO" else "secondary", use_container_width=True):
                if current_mode != "AUTO":
                    site = config['site']
                    success, error = mqtt_mgr.publish(f"wfms/{site}/cmd/mode", {
                        "cid": f"admin_{int(time.time()*1000)}",
                        "value": "AUTO",
                        "by": "admin_dashboard",
                        "ts": int(time.time())
                    })
                    if success:
                        st.session_state.current_mode = "AUTO"
                        add_log("Switched to AUTO mode", "info")
                        st.rerun()
                    else:
                        add_log(f"Mode switch failed: {error}", "error")
        with mode_cols[1]:
            if st.button("✋ MANUAL", key="mode_manual", type="primary" if current_mode == "MANUAL" else "secondary", use_container_width=True):
                if current_mode != "MANUAL":
                    site = config['site']
                    success, error = mqtt_mgr.publish(f"wfms/{site}/cmd/mode", {
                        "cid": f"admin_{int(time.time()*1000)}",
                        "value": "MANUAL",
                        "by": "admin_dashboard",
                        "ts": int(time.time())
                    })
                    if success:
                        st.session_state.current_mode = "MANUAL"
                        add_log("Switched to MANUAL mode", "warn")
                        st.rerun()
                    else:
                        add_log(f"Mode switch failed: {error}", "error")
        
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        
        # Valve control buttons (only enabled in MANUAL mode)
        if current_mode == "AUTO":
            st.markdown("""
            <div class="lock-overlay">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#9CA3AF" stroke-width="2" style="margin-bottom:8px;">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
                <p style="font-size:14px;font-weight:600;color:#D1D5DB;margin:0;">Controls Locked</p>
                <p style="font-size:12px;color:#6B7280;margin:4px 0 0 0;">Switch to MANUAL mode to operate</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            btn_cols = st.columns(2)
            with btn_cols[0]:
                if st.button("🟢 OPEN", key="valve_open", type="primary", use_container_width=True):
                    site = config['site']
                    success, error = mqtt_mgr.publish(f"wfms/{site}/cmd/valve", {
                        "cid": f"admin_{int(time.time()*1000)}",
                        "value": "ON",
                        "by": "admin_dashboard",
                        "ts": int(time.time())
                    })
                    if success:
                        add_log("Command sent: OPEN VALVE", "success")
                    else:
                        add_log(f"Failed: {error}", "error")
                    st.rerun()
            with btn_cols[1]:
                if st.button("🔴 CLOSE", key="valve_close", use_container_width=True):
                    site = config['site']
                    success, error = mqtt_mgr.publish(f"wfms/{site}/cmd/valve", {
                        "cid": f"admin_{int(time.time()*1000)}",
                        "value": "OFF",
                        "by": "admin_dashboard",
                        "ts": int(time.time())
                    })
                    if success:
                        add_log("Command sent: CLOSE VALVE", "success")
                    else:
                        add_log(f"Failed: {error}", "error")
                    st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        
        # COMMAND HISTORY
        st.markdown('<p class="section-header">📜 Recent Commands</p>', unsafe_allow_html=True)
        
        cmds = mqtt_mgr.get_commands(5)
        if cmds:
            cmd_html = '<div style="max-height:120px;overflow-y:auto;">'
            for cmd in cmds:
                cmd_time = format_time_short(cmd.get('sent_at'))
                cmd_value = cmd.get('value', '--')
                cmd_topic = cmd.get('topic', '').split('/')[-1]
                action = f"CMD: {cmd_topic.upper()} {cmd_value}"
                cmd_html += f"""
                <div class="cmd-entry">
                    <div>
                        <div class="cmd-action">{action}</div>
                        <div class="cmd-source">admin_dashboard</div>
                    </div>
                    <div class="cmd-time">{cmd_time}</div>
                </div>
                """
            cmd_html += '</div>'
            st.markdown(cmd_html, unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#6B7280;font-size:12px;text-align:center;">No commands sent yet</p>', unsafe_allow_html=True)


# =============================================================================
# NETWORK SETTING (Renamed from Configuration, MQTT only)
# =============================================================================

def render_network_setting():
    st.header("🌐 Network Setting")
    config = get_config()
    mqtt_mgr = get_mqtt_manager()
    stats = mqtt_mgr.get_stats()
    
    # Current status
    status_color = "#00E676" if stats['connected'] else "#FF5252"
    status_text = "Connected" if stats['connected'] else "Disconnected"
    
    st.markdown(f"""
    <div class="valve-card" style="margin-bottom: 20px;">
        <div style="display:flex;align-items:center;gap:12px;">
            <div style="width:12px;height:12px;border-radius:50%;background:{status_color};"></div>
            <span style="color:#FAFAFA;font-weight:600;">MQTT Status: {status_text}</span>
        </div>
        <div style="margin-top:12px;font-family:'JetBrains Mono',monospace;font-size:13px;color:#9CA3AF;">
            Current: {config['mqtt_host']}:{config['mqtt_port']} | Site: {config['site']}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    st.subheader("📝 MQTT Configuration")
    
    c1, c2 = st.columns(2)
    with c1:
        new_mqtt_host = st.text_input("MQTT Host", config['mqtt_host'])
    with c2:
        new_mqtt_port = st.number_input("MQTT Port", 1, 65535, config['mqtt_port'])
    
    c1, c2 = st.columns(2)
    with c1:
        new_mqtt_user = st.text_input("MQTT Username", config['mqtt_user'])
    with c2:
        new_mqtt_pass = st.text_input("MQTT Password", config['mqtt_pass'], type="password")
    
    new_site = st.text_input("Site ID", config['site'], help="MQTT topic prefix: wfms/{site}/...")
    
    st.divider()
    
    c1, c2, c3 = st.columns([1, 1, 2])
    
    with c1:
        if st.button("✅ Apply & Reconnect", type="primary"):
            st.session_state.config = {
                **config,
                "mqtt_host": new_mqtt_host, 
                "mqtt_port": int(new_mqtt_port),
                "mqtt_user": new_mqtt_user, 
                "mqtt_pass": new_mqtt_pass, 
                "site": new_site,
            }
            st.session_state.config_applied_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            reconnect_mqtt()
            add_log(f"Network config updated: {new_mqtt_host}:{new_mqtt_port}", "success")
            st.success("✅ Configuration applied!")
            time.sleep(1)
            st.rerun()
    
    with c2:
        if st.button("🔄 Reset to Default"):
            st.session_state.config = DEFAULT_CONFIG.copy()
            reconnect_mqtt()
            add_log("Network config reset to default", "info")
            st.rerun()
    
    # Connection test
    st.divider()
    st.subheader("🔌 Connection Test")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Status", "🟢 OK" if stats['connected'] else "🔴 Fail")
    with c2:
        st.metric("Reconnects", stats['reconnect_count'])
    with c3:
        st.metric("Last Message", format_ago(stats['last_message_time']))
    with c4:
        st.metric("Errors", stats['parse_error_count'])


# =============================================================================
# SYSTEM LOGS (Combined with all JSON/Debug data)
# =============================================================================

def render_system_logs():
    st.header("📋 System Logs & Debug Data")
    
    mqtt_mgr = get_mqtt_manager()
    stats = mqtt_mgr.get_stats()
    config = get_config()
    
    # Tabs for different log types
    tab_logs, tab_telemetry, tab_acks, tab_commands, tab_debug = st.tabs([
        "📋 Activity Logs", "📡 Telemetry Data", "✅ ACK Responses", "📤 Command History", "🔍 Debug Info"
    ])
    
    # --- ACTIVITY LOGS ---
    with tab_logs:
        c1, c2, c3 = st.columns([1, 1, 3])
        with c1:
            tail = st.selectbox("Show lines", [50, 100, 200, 500], index=1)
        with c2:
            filt = st.text_input("Filter", placeholder="keyword...", key="log_filter")
        with c3:
            st.write("")
            st.write("")
            if st.button("🔄 Refresh API Logs", key="logs_ref"):
                st.session_state.logs_data = None
        
        # Local activity logs
        st.subheader("Local Activity")
        logs = st.session_state.get('logs', [])[:tail]
        if filt:
            logs = [l for l in logs if filt.lower() in l['message'].lower()]
        
        if logs:
            log_text = "\n".join([f"[{l['time']}] [{l['type'].upper()}] {l['message']}" for l in logs])
            st.code(log_text, language="log", line_numbers=True)
        else:
            st.info("No local logs")
        
        # API logs
        st.subheader("Gateway API Logs")
        if st.session_state.logs_data is None:
            ok, data, err = api_get(f"/logs?tail={tail}")
            st.session_state.logs_data = data
            st.session_state.logs_error = err
        
        if st.session_state.logs_error:
            st.warning(f"⚠️ Cannot fetch API logs: {st.session_state.logs_error}")
        elif st.session_state.logs_data:
            api_logs = st.session_state.logs_data.get('logs', [])
            if filt:
                api_logs = [l for l in api_logs if filt.lower() in l.lower()]
            if api_logs:
                st.code("\n".join(api_logs), language="log", line_numbers=True)
            else:
                st.info("No API logs" + (f" matching '{filt}'" if filt else ""))
    
    # --- TELEMETRY DATA ---
    with tab_telemetry:
        st.subheader("📡 Raw Telemetry History")
        tele = mqtt_mgr.get_telemetry(50)
        if tele:
            st.dataframe([{
                "Time": format_time_short(t.get('ts') or t.get('received_at')),
                "Flow": f"{t.get('flow', 0):.2f}",
                "Battery": f"{t.get('battery', '--')}%",
                "Valve": t.get('valve', '--')
            } for t in tele], hide_index=True, use_container_width=True)
            
            with st.expander("📋 Raw JSON Data"):
                st.json(tele[:10])
        else:
            st.info("No telemetry data yet...")
    
    # --- ACK RESPONSES ---
    with tab_acks:
        st.subheader("✅ ACK Responses from Gateway")
        acks = mqtt_mgr.get_acks(50)
        if acks:
            log_lines = []
            for a in acks:
                ts = format_time_short(a.get('ts') or a.get('received_at'))
                ok = "✅ OK" if a.get('ok') else "❌ FAIL"
                cid = a.get('cid', '--')
                reason = a.get('reason', '')
                log_lines.append(f"[{ts}] CID={cid} {ok} {reason}")
            st.code("\n".join(log_lines), language="text")
            
            with st.expander("📋 Raw JSON Data"):
                st.json(acks[:10])
        else:
            st.info("No ACK responses yet...")
    
    # --- COMMAND HISTORY ---
    with tab_commands:
        st.subheader("📤 Sent Commands History")
        cmds = mqtt_mgr.get_commands(50)
        if cmds:
            st.dataframe([{
                "Time": format_time_short(c.get('sent_at')),
                "CID": c.get('cid', '--'),
                "Value": c.get('value', '--'),
                "Topic": c.get('topic', '--').split('/')[-1]
            } for c in cmds], hide_index=True, use_container_width=True)
            
            with st.expander("📋 Raw JSON Data"):
                st.json(cmds[:10])
        else:
            st.info("No commands sent yet...")
    
    # --- DEBUG INFO ---
    with tab_debug:
        st.subheader("🔍 Debug Information")
        
        # Current State
        st.markdown("#### Latest State")
        state = mqtt_mgr.get_state()
        if state:
            st.json(state)
        else:
            st.info("No state data")
        
        # Gateway Status
        st.markdown("#### Gateway Status")
        gateway = mqtt_mgr.get_gateway_status()
        if gateway:
            st.json(gateway)
        else:
            st.info("No gateway status")
        
        # Connection Stats
        st.markdown("#### Connection Statistics")
        st.json({
            "connected": stats['connected'],
            "mqtt_host": stats['mqtt_host'],
            "mqtt_port": stats['mqtt_port'],
            "reconnect_count": stats['reconnect_count'],
            "parse_error_count": stats['parse_error_count'],
            "telemetry_count": stats['telemetry_count'],
            "ack_count": stats['ack_count'],
            "cmd_count": stats['cmd_count'],
            "last_message": format_ago(stats['last_message_time']),
            "connect_time": format_timestamp(stats['connect_time']),
            "last_error": stats['last_error']
        })
        
        # Current Config
        st.markdown("#### Current Configuration")
        st.json(config)


# =============================================================================
# MAIN
# =============================================================================

def main():
    st.set_page_config(
        page_title=f"WFMS Admin - {DEFAULT_CONFIG['site']}", 
        page_icon="🚰",
        layout="wide", 
        initial_sidebar_state="expanded"
    )
    
    init_session_state()
    inject_custom_css()
    get_mqtt_manager()
    render_sidebar()
    
    page = st.session_state.current_page
    if page == "Live View":
        render_live_view()
    elif page == "Network Setting":
        render_network_setting()
    elif page == "System Logs":
        render_system_logs()
    else:
        # Default to Live View for any unknown page
        st.session_state.current_page = "Live View"
        render_live_view()


if __name__ == "__main__":
    main()
