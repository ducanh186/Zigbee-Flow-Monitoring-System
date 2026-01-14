"""
WFMS User Dashboard (Refactored)
================================
A modular dashboard for the Water Flow Monitoring System.

Separated logic:
- user_dashboard.py: Main entry point & MQTT logic
- styles.py: CSS & Theming
- utils.py: Helpers, Config, State Management
- views.py: UI Component Rendering

Run:
    streamlit run user_dashboard.py
"""

import sys
import os
import json
import time
import uuid
import threading
from collections import deque
from pathlib import Path
from typing import Optional, Dict, Tuple

import streamlit as st
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

# Local module imports
try:
    import styles
    import utils
    import views
except ImportError:
    from . import styles
    from . import utils
    from . import views

# =============================================================================
# Page Setup - MUST BE FIRST STREAMLIT COMMAND
# =============================================================================
st.set_page_config(
    page_title=f"WFMS User - {utils.SITE}",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =============================================================================
# MQTT Client Manager
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
        self.telemetry_buffer = deque(maxlen=utils.TELEMETRY_BUFFER_SIZE)
        self.ack_buffer = deque(maxlen=utils.ACK_BUFFER_SIZE)
        self.flow_history = deque(maxlen=utils.FLOW_HISTORY_SIZE)
        self.cmd_buffer = deque(maxlen=utils.CMD_BUFFER_SIZE)
        
        self._lock = threading.Lock()
        self._running = False
        self.client = None
        
    def start(self):
        if self._running:
            return
        try:
            client_id = f"wfms_user_{uuid.uuid4().hex[:8]}"
            self.client = mqtt.Client(client_id=client_id)
            
            if utils.MQTT_USER and utils.MQTT_PASS:
                self.client.username_pw_set(utils.MQTT_USER, utils.MQTT_PASS)
            
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            self.client.connect_async(utils.MQTT_HOST, utils.MQTT_PORT, keepalive=60)
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
                (f"wfms/{utils.SITE}/state", 1),
                (f"wfms/{utils.SITE}/telemetry", 0),
                (f"wfms/{utils.SITE}/ack", 1),
                (f"wfms/{utils.SITE}/status/gateway", 1),
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
                
                if topic == f"wfms/{utils.SITE}/state":
                    self.latest_state = data
                    # Also add to flow history
                    data['received_at'] = time.time()
                    self.flow_history.append(data)
                    
                elif topic == f"wfms/{utils.SITE}/telemetry":
                    data['received_at'] = time.time()
                    self.telemetry_buffer.appendleft(data)
                    self.flow_history.append(data)
                    # Update latest state with telemetry
                    if 'flow' in data:
                        self.latest_state['flow'] = data['flow']
                    if 'battery' in data:
                        self.latest_state['battery'] = data['battery']
                        
                elif topic == f"wfms/{utils.SITE}/ack":
                    data['received_at'] = time.time()
                    self.ack_buffer.appendleft(data)
                    
                elif topic == f"wfms/{utils.SITE}/status/gateway":
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
                'mqtt_host': utils.MQTT_HOST,
                'mqtt_port': utils.MQTT_PORT,
            }

def get_mqtt_manager():
    if 'mqtt_manager' not in st.session_state:
        st.session_state.mqtt_manager = MQTTManager()
        st.session_state.mqtt_manager.start()
    return st.session_state.mqtt_manager

# =============================================================================
# Main App
# =============================================================================
def main():
    """Main application entry point."""
    # 1. Initialize State
    utils.init_session_state()
    
    # 2. Inject CSS
    styles.inject_custom_css()
    
    # 3. Auto-refresh
    if AUTOREFRESH_AVAILABLE:
        st_autorefresh(interval=2000, limit=None, key="auto_refresh")
    
    # 4. Get/Start MQTT Manager
    mqtt_mgr = get_mqtt_manager()
    
    # 5. Render View
    views.render_dashboard(mqtt_mgr)

if __name__ == "__main__":
    main()
