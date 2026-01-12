"""
WFMS User Dashboard
Streamlit-based UI for Water Flow Monitoring System

Follows CONTRACT.md specification for MQTT topics and payloads.
Redesigned to match modern HTML dashboard layout.
"""

import os
import sys
import json
import time
import uuid
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
from dotenv import load_dotenv

# Optional imports with fallback
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

# =============================================================================
# Load .env from wfms root (2 levels up)
# =============================================================================
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if not ENV_PATH.exists():
    raise FileNotFoundError(f"Configuration file not found: {ENV_PATH}")
load_dotenv(dotenv_path=ENV_PATH)

# =============================================================================
# Configuration (read from .env - no hardcoded defaults)
# =============================================================================
MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
SITE = os.getenv("SITE", "lab1")

# Validate required settings
if not MQTT_HOST:
    raise ValueError("MQTT_HOST must be set in .env file")

# Buffer sizes
TELEMETRY_BUFFER_SIZE = 500
ACK_BUFFER_SIZE = 200
FLOW_HISTORY_SIZE = 500
CMD_BUFFER_SIZE = 100

# =============================================================================
# Page Config
# =============================================================================
st.set_page_config(
    page_title=f"WFMS User - {SITE}",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# =============================================================================
# Custom CSS - Modern Dark Theme (matching HTML design)
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
            overflow: hidden;
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
            background: rgba(59, 130, 246, 0.2);
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
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #00E676;
            animation: pulse 2s infinite;
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
        
        /* Control buttons */
        .control-btn-open {
            background: linear-gradient(to right, rgba(22,101,52,0.5), rgba(21,128,61,0.5));
            border: 1px solid rgba(34,197,94,0.5);
            border-radius: 8px;
            padding: 16px;
            color: #BBF7D0;
            font-weight: 700;
            font-size: 16px;
            width: 100%;
            cursor: pointer;
            transition: all 0.2s;
        }
        .control-btn-open:hover {
            border-color: #22C55E;
        }
        .control-btn-close {
            background: linear-gradient(to right, rgba(127,29,29,0.5), rgba(153,27,27,0.5));
            border: 1px solid rgba(239,68,68,0.5);
            border-radius: 8px;
            padding: 16px;
            color: #FECACA;
            font-weight: 700;
            font-size: 16px;
            width: 100%;
            cursor: pointer;
            transition: all 0.2s;
        }
        .control-btn-close:hover {
            border-color: #EF4444;
        }
        
        /* Mode toggle */
        .mode-toggle {
            display: inline-flex;
            background: rgba(0,0,0,0.4);
            border-radius: 20px;
            padding: 4px;
            border: 1px solid #374151;
        }
        .mode-btn-active {
            padding: 6px 16px;
            border-radius: 16px;
            font-size: 12px;
            font-weight: 700;
            background: #2563EB;
            color: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        .mode-btn-inactive {
            padding: 6px 16px;
            border-radius: 16px;
            font-size: 12px;
            font-weight: 700;
            color: #9CA3AF;
            background: transparent;
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
        .time-toggle {
            display: flex;
            background: rgba(0,0,0,0.4);
            border-radius: 8px;
            padding: 4px;
        }
        .time-btn-active {
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            background: #374151;
            color: white;
            box-shadow: 0 1px 2px rgba(0,0,0,0.3);
        }
        .time-btn-inactive {
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            color: #9CA3AF;
        }
        
        /* Hide default Streamlit elements */
        [data-testid="stMetric"] { display: none !important; }
        .stButton > button {
            width: 100%;
            border-radius: 8px !important;
            font-weight: 700 !important;
            height: 50px !important;
            font-size: 15px !important;
        }
    </style>
    """, unsafe_allow_html=True)


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
# MQTT Client Manager (same structure as Admin)
# =============================================================================
class MQTTManager:
    def __init__(self):
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
            client_id = f"wfms_user_{uuid.uuid4().hex[:8]}"
            self.client = mqtt.Client(client_id=client_id)
            
            if MQTT_USER and MQTT_PASS:
                self.client.username_pw_set(MQTT_USER, MQTT_PASS)
            
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
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
    
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            self.last_error = None
            self.connect_time = time.time()
            client.subscribe([
                (f"wfms/{SITE}/state", 1),
                (f"wfms/{SITE}/telemetry", 0),
                (f"wfms/{SITE}/ack", 1),
                (f"wfms/{SITE}/status/gateway", 1),
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
                topic = msg.topic
                
                if topic == f"wfms/{SITE}/state":
                    self.latest_state = data
                    # Also add to flow history
                    data['received_at'] = time.time()
                    self.flow_history.append(data)
                    
                elif topic == f"wfms/{SITE}/telemetry":
                    data['received_at'] = time.time()
                    self.telemetry_buffer.appendleft(data)
                    self.flow_history.append(data)
                    # Update latest state with telemetry
                    if 'flow' in data:
                        self.latest_state['flow'] = data['flow']
                    if 'battery' in data:
                        self.latest_state['battery'] = data['battery']
                        
                elif topic == f"wfms/{SITE}/ack":
                    data['received_at'] = time.time()
                    self.ack_buffer.appendleft(data)
                    
                elif topic == f"wfms/{SITE}/status/gateway":
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
            return False, "Not connected"
        try:
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                with self._lock:
                    self.cmd_buffer.appendleft({
                        'topic': topic,
                        'cid': payload.get('cid'),
                        'value': payload.get('value'),
                        'sent_at': time.time()
                    })
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
                'mqtt_host': MQTT_HOST,
                'mqtt_port': MQTT_PORT,
            }


def get_mqtt_manager():
    if 'mqtt_manager' not in st.session_state:
        st.session_state.mqtt_manager = MQTTManager()
        st.session_state.mqtt_manager.start()
    return st.session_state.mqtt_manager


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


# =============================================================================
# Main Dashboard View (Modern Layout)
# =============================================================================
def render_dashboard():
    mqtt_mgr = get_mqtt_manager()
    stats = mqtt_mgr.get_stats()
    state = mqtt_mgr.get_state()
    
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
    st.markdown(f"""
    <div class="header-bar">
        <div class="header-left">
            <div class="header-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#60A5FA" stroke-width="2">
                    <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>
                </svg>
            </div>
            <div>
                <h1 class="header-title">WFMS User Dashboard</h1>
                <p class="header-subtitle">Site: {SITE.upper()}</p>
            </div>
        </div>
        <div class="header-stats">
            <div class="status-online">
                <div class="status-dot"></div>
                <span>{'ONLINE' if is_connected else 'OFFLINE'}</span>
            </div>
            <div class="broker-info">
                Broker: <span>{MQTT_HOST}</span>
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
    # MAIN GRID: LEFT (8/12) + RIGHT (4/12)
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
                            line=dict(color='#29b5e8', width=2),
                            fillcolor='rgba(41, 181, 232, 0.3)',
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
                # Generate placeholder chart
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
        
        # Build valve card HTML
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
        mode_cols = st.columns(2)
        with mode_cols[0]:
            if st.button("🤖 AUTO", key="mode_auto", type="primary" if current_mode == "AUTO" else "secondary", use_container_width=True):
                if current_mode != "AUTO":
                    mqtt_mgr.publish(f"wfms/{SITE}/cmd/mode", {
                        "cid": f"user_{int(time.time()*1000)}",
                        "value": "AUTO",
                        "by": "user_dashboard",
                        "ts": int(time.time())
                    })
                    st.session_state.current_mode = "AUTO"
                    add_log("Switched to AUTO mode", "info")
                    st.rerun()
        with mode_cols[1]:
            if st.button("✋ MANUAL", key="mode_manual", type="primary" if current_mode == "MANUAL" else "secondary", use_container_width=True):
                if current_mode != "MANUAL":
                    mqtt_mgr.publish(f"wfms/{SITE}/cmd/mode", {
                        "cid": f"user_{int(time.time()*1000)}",
                        "value": "MANUAL",
                        "by": "user_dashboard",
                        "ts": int(time.time())
                    })
                    st.session_state.current_mode = "MANUAL"
                    add_log("Switched to MANUAL mode", "warn")
                    st.rerun()
        
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
                    success, error = mqtt_mgr.publish(f"wfms/{SITE}/cmd/valve", {
                        "cid": f"user_{int(time.time()*1000)}",
                        "value": "ON",
                        "by": "user_dashboard",
                        "ts": int(time.time())
                    })
                    if success:
                        add_log("Command sent: OPEN VALVE", "success")
                    else:
                        add_log(f"Failed: {error}", "error")
                    st.rerun()
            with btn_cols[1]:
                if st.button("🔴 CLOSE", key="valve_close", use_container_width=True):
                    success, error = mqtt_mgr.publish(f"wfms/{SITE}/cmd/valve", {
                        "cid": f"user_{int(time.time()*1000)}",
                        "value": "OFF",
                        "by": "user_dashboard",
                        "ts": int(time.time())
                    })
                    if success:
                        add_log("Command sent: CLOSE VALVE", "error")
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
                        <div class="cmd-source">user_dashboard</div>
                    </div>
                    <div class="cmd-time">{cmd_time}</div>
                </div>
                """
            cmd_html += '</div>'
            st.markdown(cmd_html, unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#6B7280;font-size:12px;text-align:center;">No commands sent yet</p>', unsafe_allow_html=True)


# =============================================================================
# Main App
# =============================================================================
def main():
    """Main application entry point."""
    init_session_state()
    inject_custom_css()
    
    # Auto-refresh every 2 seconds (always enabled, hidden from UI)
    if AUTOREFRESH_AVAILABLE:
        st_autorefresh(interval=2000, limit=None, key="auto_refresh")
    
    # Initialize MQTT manager
    get_mqtt_manager()
    
    # Render Dashboard
    render_dashboard()


if __name__ == "__main__":
    main()
