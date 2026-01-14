"""
WFMS Admin Dashboard - Streamlit Application
=============================================
A production-ready admin dashboard for the Water Flow Monitoring System.

Separated logic:
- admin_dashboard.py: Main entry point & MQTT logic
- styles.py: CSS & Theming
- utils.py: Helpers, Config, State Management
- views.py: UI Component Rendering

Run:
    streamlit run admin_dashboard.py
"""

import os
import json
import time
import uuid
import threading
import pathlib
from collections import deque
import streamlit as st
import paho.mqtt.client as mqtt

# Local module imports
try:
    import styles
    import utils
    import views
except ImportError:
    # Fallback for running from parent directory or different context
    from . import styles
    from . import utils
    from . import views

# =============================================================================
# MQTT CLIENT MANAGER
# =============================================================================

class MQTTManager:
    def __init__(self, config):
        self._config = config.copy()
        self.connected = False
        self.last_error = None
        self.last_message_time = None
        self.parse_error_count = 0
        self.reconnect_count = 0
        self.connect_time = None
        
        self.latest_state = {}
        self.gateway_status = {}
        # Buffer sizes defined in utils or locally
        self.telemetry_buffer = deque(maxlen=500)
        self.ack_buffer = deque(maxlen=200)
        self.flow_history = deque(maxlen=500)
        self.cmd_buffer = deque(maxlen=100)
        
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
    
    def reconnect(self, new_config):
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
                elif msg.topic == f"wfms/{site}/telemetry":
                    data['received_at'] = time.time()
                    self.telemetry_buffer.appendleft(data)
                    self.flow_history.append({
                        'time': utils.format_timestamp(data.get('ts', time.time())),
                        'flow': data.get('flow', 0)
                    })
                elif msg.topic == f"wfms/{site}/ack":
                    data['ts'] = time.time()
                    self.ack_buffer.appendleft(data)
                    # Log ACK
                    result = "SUCCESS" if data.get('ok') else "FAIL"
                    utils.add_log(f"CMD ACK: {data.get('cid')} -> {result}", 
                                  "success" if data.get('ok') else "error")
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
    
    def publish(self, topic: str, payload):
        """Publish a message to MQTT broker"""
        if not self.connected or not self.client:
            return False, "Not connected to MQTT broker"
        try:
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                with self._lock:
                    self.cmd_buffer.appendleft({
                        'topic': topic,
                        'value': payload.get('value'),
                        'mode': payload.get('mode'),
                        'sent_at': time.time()
                    })
                return True, None
            else:
                return False, f"MQTT Error: {result.rc}"
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
    config = utils.get_config()
    if 'mqtt_manager' not in st.session_state:
        st.session_state.mqtt_manager = MQTTManager(config)
        st.session_state.mqtt_manager.start()
    return st.session_state.mqtt_manager

def reconnect_mqtt():
    """Reconnect wrapper used by main logic"""
    config = utils.get_config()
    if 'mqtt_manager' in st.session_state:
        st.session_state.mqtt_manager.reconnect(config)

# =============================================================================
# MAIN
# =============================================================================

def main():
    st.set_page_config(
        page_title=f"WFMS Admin", 
        page_icon="🚰",
        layout="wide", 
        initial_sidebar_state="expanded"
    )
    
    utils.init_session_state()
    styles.inject_custom_css()
    mqtt_mgr = get_mqtt_manager()
    
    views.render_sidebar(mqtt_mgr)
    
    page = st.session_state.current_page
    if page == "Live View":
        views.render_live_view(mqtt_mgr)
    elif page == "Network Setting":
        views.render_network_setting(mqtt_mgr)
    elif page == "System Logs":
        views.render_system_logs(mqtt_mgr)
    else:
        st.session_state.current_page = "Live View"
        views.render_live_view(mqtt_mgr)

if __name__ == "__main__":
    main()
