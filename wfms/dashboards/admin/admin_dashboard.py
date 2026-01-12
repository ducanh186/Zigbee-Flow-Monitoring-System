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
    if "health_data" not in st.session_state:
        st.session_state.health_data = None
    if "health_error" not in st.session_state:
        st.session_state.health_error = None
    if "rules_data" not in st.session_state:
        st.session_state.rules_data = None
    if "logs_data" not in st.session_state:
        st.session_state.logs_data = None
    if "logs_error" not in st.session_state:
        st.session_state.logs_error = None
    if "current_mode" not in st.session_state:
        st.session_state.current_mode = "AUTO"  # Default mode


def get_config() -> Dict:
    if "config" not in st.session_state:
        st.session_state.config = DEFAULT_CONFIG.copy()
    return st.session_state.config


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
                    # Track mode from state
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
                # Track command in buffer
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


def get_available_com_ports():
    try:
        import serial.tools.list_ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports:
            return sorted(ports)
    except:
        pass
    return [f"COM{i}" for i in range(1, 31)]


# =============================================================================
# CUSTOM CSS
# =============================================================================

def inject_custom_css():
    st.markdown("""
    <style>
        .stApp { background-color: #0E1117; }
        h1 { font-family: 'Segoe UI', sans-serif; font-weight: 700; color: #E0E0E0; text-shadow: 0 0 10px rgba(255,255,255,0.1); }
        [data-testid="stMetric"] { 
            background-color: #262626; 
            padding: 15px 20px; 
            border-radius: 10px; 
            border: 1px solid #383838; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.3); 
            transition: transform 0.2s; 
        }
        [data-testid="stMetric"]:hover { border-color: #666; transform: translateY(-2px); }
        [data-testid="stMetricLabel"] { font-size: 16px !important; color: #A0A0A0 !important; font-weight: 500; }
        [data-testid="stMetricValue"] { font-size: 36px !important; font-weight: 700 !important; color: #FFFFFF !important; font-family: 'Roboto Mono', monospace; }
        [data-testid="stMetricDelta"] svg { transform: scale(1.2); }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: transparent; }
        .stTabs [data-baseweb="tab"] { height: 55px; background-color: #1E1E1E; border-radius: 8px; color: #B0B0B0; font-weight: 600; border: 1px solid #333; padding: 0 25px; }
        .stTabs [aria-selected="true"] { background-color: #FF4B4B !important; color: white !important; border-color: #FF4B4B !important; box-shadow: 0 0 10px rgba(255, 75, 75, 0.4); }
        .stButton button { font-weight: bold; border-radius: 6px; height: 45px; }
        .kpi-header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border: 1px solid #30305a;
            border-radius: 10px;
            padding: 15px 20px;
            margin-bottom: 20px;
        }
        .kpi-header span { color: #ffffff; margin-right: 30px; }
        .kpi-header .kpi-value { color: #4CAF50; font-weight: 600; }
        .block-container { padding-top: 1rem; }
        .valve-status-box {
            text-align: center;
            margin-bottom: 20px;
        }
        .valve-icon { font-size: 60px; }
        .valve-label { font-size: 28px; font-weight: bold; text-transform: uppercase; }
        .valve-caption { color: #888; font-size: 14px; }
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
            pages = ["Live View", "Panel Health", "Rule Control", "Configuration", "System Logs"]
            selected = option_menu(
                menu_title=None,
                options=pages,
                icons=["activity", "heart-pulse", "sliders", "gear", "file-text"],
                default_index=pages.index(st.session_state.current_page),
                styles={
                    "container": {"padding": "0", "background-color": "#0e1117"},
                    "icon": {"color": "#4CAF50", "font-size": "18px"},
                    "nav-link": {"font-size": "14px", "text-align": "left", "margin": "2px", "padding": "10px 15px"},
                    "nav-link-selected": {"background-color": "#1a1a2e", "border-left": "4px solid #4CAF50"},
                }
            )
            st.session_state.current_page = selected
        else:
            st.subheader("📍 Navigation")
            for label, page in [("📊 Live View", "Live View"), ("🏥 Panel Health", "Panel Health"),
                                ("⚙️ Rule Control", "Rule Control"), ("🔧 Configuration", "Configuration"),
                                ("📋 System Logs", "System Logs")]:
                if st.session_state.current_page == page:
                    st.markdown(f"**→ {label}**")
                elif st.button(label, key=f"nav_{page}"):
                    st.session_state.current_page = page
                    st.rerun()
        
        st.divider()
        st.subheader("🔌 Connections")
        st.text(f"API: {config['api_base_url']}")
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
# LIVE VIEW
# =============================================================================

def render_live_view():
    mqtt_mgr = get_mqtt_manager()
    stats = mqtt_mgr.get_stats()
    state = mqtt_mgr.get_state()
    
    # --- HEADER ---
    st.title("📡 Zigbee Gateway Operator")
    st.markdown("---")
    
    # --- QUICK STATS ROW (5 metrics) ---
    stat_col1, stat_col2, stat_col3, stat_col4, stat_col5 = st.columns(5)
    with stat_col1:
        is_connected = stats['connected']
        status_text = "ONLINE" if is_connected else "OFFLINE"
        st.metric(
            "System Status", 
            status_text, 
            delta="Connected" if is_connected else "- Disconnected",
            delta_color="normal" if is_connected else "inverse"
        )
    with stat_col2:
        st.metric("RX Lines", f"{stats.get('telemetry_count', 0):,}")
    with stat_col3:
        st.metric("TX Cmds", f"{stats.get('cmd_count', 0):,}")
    with stat_col4:
        # Count telemetry as data packets
        tele_count = len(mqtt_mgr.get_telemetry(100))
        st.metric("Data Pkts", f"{tele_count:,}")
    with stat_col5:
        err = stats.get("last_error", "")
        if err:
            st.error(f"Error: {err}")
        else:
            st.metric("Errors", "None", delta_color="off")
    
    # --- VALVE CONTROL SECTION ---
    st.subheader("🎮 Valve Control")
    
    # Mode selector row
    mode_col1, mode_col2, mode_col3 = st.columns([1, 1, 2])
    
    with mode_col1:
        current_mode = st.session_state.get('current_mode', 'AUTO')
        # Extract mode from state if available
        if state and isinstance(state, dict) and 'mode' in state:
            current_mode = state.get('mode', 'AUTO').upper()
            st.session_state.current_mode = current_mode
        
        st.markdown(f"**Current Mode:** {'🤖 AUTO' if current_mode == 'AUTO' else '✋ MANUAL'}")
    
    with mode_col2:
        if st.button("🤖 AUTO Mode" if current_mode == "MANUAL" else "✋ MANUAL Mode", 
                     key="mode_toggle", use_container_width=True):
            config = get_config()
            site = config['site']
            new_mode = "AUTO" if current_mode == "MANUAL" else "MANUAL"
            mode_payload = {
                "cid": f"web_{int(time.time()*1000)}",
                "value": new_mode
            }
            topic = f"wfms/{site}/cmd/mode"
            success, error = mqtt_mgr.publish(topic, mode_payload)
            if success:
                st.session_state.current_mode = new_mode
                st.success(f"✅ Switched to {new_mode}")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"❌ Failed: {error}")
    
    with mode_col3:
        if current_mode == "AUTO":
            st.info("🤖 Sensor controls valve automatically")
        else:
            st.warning("✋ Manual control active")
    
    st.divider()
    
    # Valve control buttons
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1, 1, 2])
    
    with ctrl_col1:
        if st.button("🟢 OPEN VALVE", key="valve_open", type="primary", use_container_width=True):
            config = get_config()
            site = config['site']
            current_mode = st.session_state.get('current_mode', 'AUTO')
            
            # If in AUTO mode, switch to MANUAL first
            if current_mode == "AUTO":
                mode_payload = {
                    "cid": f"web_{int(time.time()*1000)}",
                    "value": "MANUAL"
                }
                mode_topic = f"wfms/{site}/cmd/mode"
                mode_success, mode_error = mqtt_mgr.publish(mode_topic, mode_payload)
                if mode_success:
                    st.session_state.current_mode = "MANUAL"
                    st.info("🔄 Auto-switched to MANUAL")
                    time.sleep(0.3)
                else:
                    st.error(f"❌ Mode switch failed: {mode_error}")
                    return
            
            # Send valve command
            cmd_payload = {
                "cid": f"web_{int(time.time()*1000)}",
                "value": "ON"
            }
            topic = f"wfms/{site}/cmd/valve"
            success, error = mqtt_mgr.publish(topic, cmd_payload)
            if success:
                st.success("✅ Command sent: OPEN")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"❌ Failed: {error}")
    
    with ctrl_col2:
        if st.button("🔴 CLOSE VALVE", key="valve_close", use_container_width=True):
            config = get_config()
            site = config['site']
            current_mode = st.session_state.get('current_mode', 'AUTO')
            
            # If in AUTO mode, switch to MANUAL first
            if current_mode == "AUTO":
                mode_payload = {
                    "cid": f"web_{int(time.time()*1000)}",
                    "value": "MANUAL"
                }
                mode_topic = f"wfms/{site}/cmd/mode"
                mode_success, mode_error = mqtt_mgr.publish(mode_topic, mode_payload)
                if mode_success:
                    st.session_state.current_mode = "MANUAL"
                    st.info("🔄 Auto-switched to MANUAL")
                    time.sleep(0.3)
                else:
                    st.error(f"❌ Mode switch failed: {mode_error}")
                    return
            
            # Send valve command
            cmd_payload = {
                "cid": f"web_{int(time.time()*1000)}",
                "value": "OFF"
            }
            topic = f"wfms/{site}/cmd/valve"
            success, error = mqtt_mgr.publish(topic, cmd_payload)
            if success:
                st.success("✅ Command sent: CLOSE")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"❌ Failed: {error}")
    
    with ctrl_col3:
        # Show recent commands
        recent_cmds = mqtt_mgr.get_commands(5)
        if recent_cmds:
            st.markdown("**Recent Commands:**")
            for cmd in recent_cmds:
                cid = cmd.get('cid', 'unknown')
                value = cmd.get('value', '')
                sent_time = format_time_short(cmd.get('sent_at'))
                topic_type = cmd.get('topic', '').split('/')[-1]
                icon = "🎚️" if topic_type == "mode" else "🎮"
                st.caption(f"{icon} {sent_time}: {value}")
        else:
            st.caption("No commands sent yet")
    
    st.divider()
    
    # --- MONITORING SECTION (Current State + Charts) ---
    st.subheader("📊 Live Telemetry")
    
    # Get valve state for display
    valve_state = None
    latest_flow = None
    latest_battery = None
    
    if state and isinstance(state, dict):
        valve_raw = state.get('valve', 'unknown')
        if isinstance(valve_raw, str):
            valve_state = valve_raw.lower()
            if valve_state == 'close':
                valve_state = 'closed'
            elif valve_state == 'on':
                valve_state = 'open'
            elif valve_state == 'off':
                valve_state = 'closed'
        latest_flow = state.get('flow')
        latest_battery = state.get('battery')
    
    # Two columns: Left = Current State, Right = Charts
    mon_c1, mon_c2 = st.columns([1.2, 2.5])
    
    with mon_c1:
        st.markdown("##### Current State")
        with st.container(border=True):
            if state and isinstance(state, dict):
                # Valve status with big icon
                v_color = "#00E676" if valve_state == "open" else "#FF5252"
                v_icon = "💧" if valve_state == "open" else "🚫"
                st.markdown(
                    f"""
                    <div style='text-align: center; margin-bottom: 20px;'>
                        <div style='font-size: 60px;'>{v_icon}</div>
                        <div style='font-size: 28px; font-weight: bold; color: {v_color}; text-transform: uppercase;'>
                            {str(valve_state or 'unknown')}
                        </div>
                        <div style='color: #888; font-size: 14px;'>VALVE STATUS</div>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                st.divider()
                c_flow, c_bat = st.columns(2)
                flow_val = f"{latest_flow:.1f}" if isinstance(latest_flow, (int, float)) else "--"
                bat_val = f"{latest_battery}" if latest_battery is not None else "--"
                c_flow.metric("Flow Rate", flow_val, "L/min")
                c_bat.metric("Battery", f"{bat_val}%", "Level")
            else:
                st.warning("Waiting for @DATA...")
                st.metric("Flow", "--")
                st.metric("Battery", "--")
    
    with mon_c2:
        # Get flow data for charts
        flow_data = mqtt_mgr.get_flow_history(200)
        
        if flow_data and len(flow_data) > 0:
            # Time window selector
            window = st.selectbox("Time Window", ["All", "5 min", "15 min", "60 min"], key="flow_window")
            
            now = time.time()
            cutoff = now - {"All": 999999, "5 min": 300, "15 min": 900, "60 min": 3600}.get(window, 999999)
            filtered = [d for d in flow_data if d.get('received_at', d.get('ts', 0)) >= cutoff]
            
            if filtered:
                df = pd.DataFrame(filtered)
                df['time'] = pd.to_datetime(df['received_at'].apply(datetime.fromtimestamp))
                
                # Tabs for Flow and Battery history
                tab_flow, tab_bat = st.tabs(["🌊 Flow History", "🔋 Battery History"])
                
                with tab_flow:
                    if PLOTLY_AVAILABLE:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=df['time'], y=df['flow'], 
                            mode='lines+markers',
                            line=dict(color='#29b5e8', width=2), 
                            marker=dict(size=4),
                            name='Flow'
                        ))
                        fig.update_layout(
                            xaxis_title="Time", 
                            yaxis_title="Flow (L/min)", 
                            template="plotly_dark",
                            height=280, 
                            margin=dict(l=50, r=20, t=30, b=50),
                            paper_bgcolor='#1a1a2e', 
                            plot_bgcolor='#1a1a2e'
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.line_chart(df.set_index('time')['flow'], height=280, color='#29b5e8')
                
                with tab_bat:
                    # If we have battery data, show it
                    if state and state.get('battery') is not None:
                        battery_val = state.get('battery', 0)
                        # Create simple battery display since we may not have history
                        st.markdown(f"### 🔋 Current: {battery_val}%")
                        st.progress(min(100, max(0, int(battery_val))) / 100)
                        if PLOTLY_AVAILABLE:
                            # Create a gauge-like display
                            fig = go.Figure(go.Indicator(
                                mode="gauge+number",
                                value=battery_val,
                                domain={'x': [0, 1], 'y': [0, 1]},
                                gauge={
                                    'axis': {'range': [0, 100]},
                                    'bar': {'color': "#4cd137"},
                                    'bgcolor': "#1a1a2e",
                                    'borderwidth': 2,
                                    'bordercolor': "#333",
                                    'steps': [
                                        {'range': [0, 20], 'color': '#FF5252'},
                                        {'range': [20, 50], 'color': '#FFC107'},
                                        {'range': [50, 100], 'color': '#4cd137'}
                                    ]
                                },
                                title={'text': "Battery Level", 'font': {'color': '#fff'}}
                            ))
                            fig.update_layout(
                                height=250,
                                paper_bgcolor='#1a1a2e',
                                font={'color': '#fff'}
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("Battery data not available")
            else:
                st.info("No data in selected window")
        else:
            st.info("📊 Waiting for data...")
    
    st.divider()
    
    # --- RESPONSE INSPECTOR (Latest ACKs & Info) ---
    st.subheader("📝 Response Inspector")
    
    r1, r2, r3 = st.columns(3)
    with r1:
        with st.container(border=True):
            st.markdown("**Latest State**")
            if state:
                st.json(state, expanded=False)
                if state.get('ts') or state.get('updatedAt'):
                    ts_val = state.get('ts') or state.get('updatedAt')
                    st.caption(f"Time: {format_time_short(ts_val)}")
            else:
                st.caption("No data")
    
    with r2:
        with st.container(border=True):
            st.markdown("**Gateway Status**")
            gateway = mqtt_mgr.get_gateway_status()
            if gateway:
                st.json(gateway, expanded=False)
                if gateway.get('ts'):
                    st.caption(f"Time: {format_time_short(gateway.get('ts'))}")
            else:
                st.caption("No data")
    
    with r3:
        with st.container(border=True):
            st.markdown("**Connection Stats**")
            st.json({
                "connected": stats['connected'],
                "mqtt_host": stats['mqtt_host'],
                "mqtt_port": stats['mqtt_port'],
                "reconnects": stats['reconnect_count'],
                "last_msg": format_ago(stats['last_message_time'])
            }, expanded=False)
    
# --- RAW DATA TABLES ---
    c1, c2 = st.columns(2)
    with c1:
        with st.expander("📂 Raw Telemetry History", expanded=False):
            tele = mqtt_mgr.get_telemetry(30)
            if tele:
                st.dataframe([{
                    "Time": format_time_short(t.get('ts') or t.get('received_at')),
                    "Flow": f"{t.get('flow', 0):.2f}",
                    "Battery": f"{t.get('battery', '--')}%",
                    "Valve": t.get('valve', '--')
                } for t in tele], hide_index=True, use_container_width=True)
            else:
                st.info("No telemetry data yet...")
    
    with c2:
        with st.expander("📜 Terminal Log (ACKs)", expanded=False):
            acks = mqtt_mgr.get_acks(30)
            if acks:
                log_lines = []
                for a in acks:
                    ts = format_time_short(a.get('ts') or a.get('received_at'))
                    ok = "OK" if a.get('ok') else "FAIL"
                    cid = a.get('cid', '--')
                    reason = a.get('reason', '')
                    log_lines.append(f"[{ts}] CID={cid} {ok} {reason}")
                st.code("\n".join(log_lines) if log_lines else "(empty)", language="text")
            else:
                st.code("(empty)", language="text")
    
    # Command history
    with st.expander("📤 Sent Commands History", expanded=False):
        cmds = mqtt_mgr.get_commands(30)
        if cmds:
            st.dataframe([{
                "Time": format_time_short(c.get('sent_at')),
                "CID": c.get('cid', '--'),
                "Value": c.get('value', '--'),
                "Topic": c.get('topic', '--').split('/')[-1]
            } for c in cmds], hide_index=True, use_container_width=True)
        else:
            st.info("No commands sent yet...")
    
    # Debug expander
    with st.expander("🔍 Debug Info"):
        st.json({"gateway": mqtt_mgr.get_gateway_status(), "state": mqtt_mgr.get_state(), "stats": stats})


# =============================================================================
# PANEL HEALTH
# =============================================================================

def render_panel_health():
    st.header("🏥 Panel Health")
    mqtt_mgr = get_mqtt_manager()
    stats = mqtt_mgr.get_stats()
    
    if st.button("🔄 Refresh", key="health_ref"):
        st.session_state.health_data = None
    
    if st.session_state.health_data is None:
        ok, data, err = api_get("/health")
        st.session_state.health_data = data
        st.session_state.health_error = err
    
    st.divider()
    st.subheader("🌐 Gateway Health")
    
    health = st.session_state.health_data
    if st.session_state.health_error:
        st.error(f"❌ {st.session_state.health_error}")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Status", f"{'🟢' if health and health.get('status') == 'ok' else '🔴'} {health.get('status', 'N/A').upper() if health else 'N/A'}")
    with c2:
        st.metric("Uptime", format_uptime(health.get('uptime')) if health else "N/A")
    with c3:
        st.metric("Version", health.get('version', health.get('build', 'N/A')) if health else "N/A")
    with c4:
        st.metric("Updated", format_timestamp(health.get('ts')) if health else "N/A")
    
    st.divider()
    st.subheader("🔌 Connectivity")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("MQTT", f"{'🟢 Connected' if stats['connected'] else '🔴 Disconnected'}")
    with c2:
        st.metric("Reconnects", stats['reconnect_count'])
    with c3:
        st.metric("Last Msg", format_ago(stats['last_message_time']))
    with c4:
        uart = health.get('uart', 'N/A') if health else 'N/A'
        st.metric("UART", f"{'🟢' if uart in ['connected', True, 'ok'] else '🔴'} {uart}")
    
    st.divider()
    st.subheader("📡 Nodes")
    
    if health and 'nodes' in health and health['nodes']:
        st.dataframe([{"ID": n.get('id', '--'), "Type": n.get('type', '--'),
                       "Status": "🟢" if n.get('online') else "🔴",
                       "Battery": f"{n.get('battery', '--')}%",
                       "Last Seen": format_ago(n.get('last_seen'))} for n in health['nodes']], hide_index=True)
    else:
        state = mqtt_mgr.get_state()
        if state:
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Valve Node", state.get('valveNodeId', 'N/A'))
            with c2:
                st.metric("Known", "Yes" if state.get('valveKnown') else "No")
        else:
            st.info("No node data")
    
    with st.expander("🔍 Raw"):
        st.json(health or {})


# =============================================================================
# RULE CONTROL
# =============================================================================

def render_rule_control():
    st.header("⚙️ Rule Control")
    
    if st.button("📥 Load", key="rules_load"):
        st.session_state.rules_data = None
    
    if st.session_state.rules_data is None:
        ok, data, err = api_get("/rules")
        if ok:
            st.session_state.rules_data = data
        else:
            st.warning(f"⚠️ {err}")
            st.session_state.rules_data = {'lock': False, 'cooldown_user_s': 0, 'cooldown_global_s': 0,
                                           'dedupe_ttl_s': 60, 'ack_timeout_s': 3}
    
    rules = st.session_state.rules_data or {}
    st.divider()
    
    st.subheader("🔒 System Lock")
    new_lock = st.toggle("Enable Lock", rules.get('lock', False))
    if new_lock:
        st.error("⚠️ SYSTEM LOCKED")
    
    st.divider()
    st.subheader("⏱️ Cooldowns")
    
    c1, c2 = st.columns(2)
    with c1:
        new_user_cd = st.number_input("User (s)", 0, 3600, int(rules.get('cooldown_user_s', 0)))
    with c2:
        new_global_cd = st.number_input("Global (s)", 0, 3600, int(rules.get('cooldown_global_s', 0)))
    
    with st.expander("🔧 Advanced"):
        c1, c2 = st.columns(2)
        with c1:
            new_dedupe = st.number_input("Dedupe TTL (s)", 0, 3600, int(rules.get('dedupe_ttl_s', 60)))
        with c2:
            new_ack_to = st.number_input("ACK Timeout (s)", 1, 60, int(rules.get('ack_timeout_s', 3)))
    
    st.divider()
    if st.button("✅ Apply", type="primary"):
        payload = {}
        if new_lock != rules.get('lock'): payload['lock'] = new_lock
        if new_user_cd != rules.get('cooldown_user_s'): payload['cooldown_user_s'] = new_user_cd
        if new_global_cd != rules.get('cooldown_global_s'): payload['cooldown_global_s'] = new_global_cd
        if new_dedupe != rules.get('dedupe_ttl_s'): payload['dedupe_ttl_s'] = new_dedupe
        if new_ack_to != rules.get('ack_timeout_s'): payload['ack_timeout_s'] = new_ack_to
        
        if payload:
            ok, _, err = api_post("/rules", payload)
            if ok:
                st.success("✅ Applied!")
                st.session_state.rules_data.update(payload)
            else:
                st.error(f"❌ {err}")
        else:
            st.info("No changes")
    
    with st.expander("📋 Current"):
        st.json(rules)


# =============================================================================
# CONFIGURATION
# =============================================================================

def render_configuration():
    st.header("🔧 Configuration")
    config = get_config()
    
    st.info(f"**Current:** API: `{config['api_base_url']}` | MQTT: `{config['mqtt_host']}:{config['mqtt_port']}` | Site: `{config['site']}`")
    st.divider()
    
    st.subheader("📝 Edit")
    
    new_api = st.text_input("API URL", config['api_base_url'])
    
    c1, c2 = st.columns(2)
    with c1:
        new_mqtt_host = st.text_input("MQTT Host", config['mqtt_host'])
    with c2:
        new_mqtt_port = st.number_input("MQTT Port", 1, 65535, config['mqtt_port'])
    
    c1, c2 = st.columns(2)
    with c1:
        new_mqtt_user = st.text_input("MQTT User", config['mqtt_user'])
    with c2:
        new_mqtt_pass = st.text_input("MQTT Pass", config['mqtt_pass'], type="password")
    
    new_site = st.text_input("Site", config['site'])
    
    c1, c2 = st.columns(2)
    with c1:
        ports = get_available_com_ports()
        if config['uart_port'] not in ports:
            ports.append(config['uart_port'])
        new_uart = st.selectbox("UART", sorted(ports), index=sorted(ports).index(config['uart_port']) if config['uart_port'] in ports else 0)
    with c2:
        bauds = [9600, 19200, 38400, 57600, 115200]
        new_baud = st.selectbox("Baud", bauds, index=bauds.index(config['uart_baud']) if config['uart_baud'] in bauds else 4)
    
    st.divider()
    c1, c2, c3 = st.columns([1, 1, 3])
    
    with c1:
        if st.button("✅ Apply", type="primary"):
            st.session_state.config = {
                "api_base_url": new_api, "mqtt_host": new_mqtt_host, "mqtt_port": int(new_mqtt_port),
                "mqtt_user": new_mqtt_user, "mqtt_pass": new_mqtt_pass, "site": new_site,
                "uart_port": new_uart, "uart_baud": int(new_baud),
            }
            st.session_state.config_applied_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            reconnect_mqtt()
            st.success("✅ Applied!")
            time.sleep(1)
            st.rerun()
    
    with c2:
        if st.button("📤 Sync Gateway"):
            ok, _, err = api_post("/config", {"uart_port": new_uart, "uart_baud": int(new_baud)})
            st.success("✅ Synced!") if ok else st.error(f"❌ {err}")
    
    with st.expander("📋 JSON"):
        st.json(config)
    
    st.divider()
    if st.button("🔄 Reset"):
        st.session_state.config = DEFAULT_CONFIG.copy()
        reconnect_mqtt()
        st.rerun()


# =============================================================================
# SYSTEM LOGS
# =============================================================================

def render_system_logs():
    st.header("📋 System Logs")
    
    c1, c2, c3 = st.columns([1, 1, 3])
    with c1:
        tail = st.selectbox("Lines", [100, 200, 500, 1000], index=1)
    with c2:
        filt = st.text_input("Filter", placeholder="keyword...")
    with c3:
        st.write("")
        st.write("")
        refresh = st.button("🔄 Refresh", key="logs_ref")
    
    if refresh or st.session_state.logs_data is None:
        ok, data, err = api_get(f"/logs?tail={tail}")
        st.session_state.logs_data = data
        st.session_state.logs_error = err
    
    st.divider()
    
    if st.session_state.logs_error:
        st.error(f"❌ {st.session_state.logs_error}")
    
    if st.session_state.logs_data:
        logs = st.session_state.logs_data.get('logs', [])
        if filt:
            logs = [l for l in logs if filt.lower() in l.lower()]
            st.caption(f"Filtered: {len(logs)} lines")
        if logs:
            st.code("\n".join(logs), language="log", line_numbers=True)
        else:
            st.info("No logs" + (f" matching '{filt}'" if filt else ""))
    else:
        st.info("Click Refresh")


# =============================================================================
# MAIN
# =============================================================================

def main():
    st.set_page_config(page_title=f"WFMS Admin - {DEFAULT_CONFIG['site']}", page_icon="🚰",
                       layout="wide", initial_sidebar_state="expanded")
    
    init_session_state()
    inject_custom_css()
    get_mqtt_manager()
    render_sidebar()
    
    page = st.session_state.current_page
    if page == "Live View":
        render_live_view()
    elif page == "Panel Health":
        render_panel_health()
    elif page == "Rule Control":
        render_rule_control()
    elif page == "Configuration":
        render_configuration()
    elif page == "System Logs":
        render_system_logs()


if __name__ == "__main__":
    main()
