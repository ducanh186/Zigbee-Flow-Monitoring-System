"""
Zigbee Dashboard - Streamlit UI
Dashboard đẹp với cards màu, charts theo giờ/ngày, và điều khiển valve
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import time
from datetime import datetime, timedelta
from pc_gateway import ZigbeeGateway


# Page config
st.set_page_config(
    page_title="Zigbee Dashboard",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .big-metric {
        font-size: 48px !important;
        font-weight: bold;
        margin: 0;
    }
    .metric-label {
        font-size: 18px;
        color: #666;
        margin-bottom: 10px;
    }
    .status-badge {
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        display: inline-block;
    }
    .status-open {
        background-color: #d4edda;
        color: #155724;
    }
    .status-closed {
        background-color: #f8d7da;
        color: #721c24;
    }
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)


# Initialize session state
if 'gateway' not in st.session_state:
    st.session_state.gateway = ZigbeeGateway()
    st.session_state.connected = False
    st.session_state.selected_port = None
    st.session_state.last_data = {}
    st.session_state.last_update = None
    st.session_state.ack_status = None

if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True


def format_timestamp(ts):
    """Format timestamp thành string đẹp"""
    if ts:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%H:%M:%S")
    return "N/A"


def get_battery_color(battery):
    """Màu theo % pin"""
    if battery >= 80:
        return "#28a745"  # Green
    elif battery >= 50:
        return "#ffc107"  # Yellow
    elif battery >= 20:
        return "#fd7e14"  # Orange
    else:
        return "#dc3545"  # Red


def get_flow_status(flow, close_th=80, open_th=20):
    """Status flow theo threshold"""
    if flow >= close_th:
        return "HIGH", "#dc3545"
    elif flow <= open_th:
        return "LOW", "#28a745"
    else:
        return "NORMAL", "#17a2b8"


# Callbacks
def on_data_received(data):
    """Callback khi nhận data từ gateway"""
    st.session_state.last_data = data
    st.session_state.last_update = time.time()


def on_ack_received(data):
    """Callback khi nhận ACK"""
    st.session_state.ack_status = data


def on_connection_changed(connected, info):
    """Callback khi connection thay đổi"""
    st.session_state.connected = connected


# Setup callbacks
st.session_state.gateway.on_data_callback = on_data_received
st.session_state.gateway.on_ack_callback = on_ack_received
st.session_state.gateway.on_connection_change = on_connection_changed


# ===== SIDEBAR =====
with st.sidebar:
    st.title("⚙️ Configuration")
    
    # COM Port selection
    st.subheader("Serial Connection")
    ports = st.session_state.gateway.list_ports()
    port_options = [f"{p[0]} - {p[1]}" for p in ports] if ports else ["No ports found"]
    
    selected = st.selectbox("COM Port", port_options, key="port_select")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Connect", type="primary", disabled=st.session_state.connected):
            if ports:
                port = ports[0][0]  # Extract port from selection
                if st.session_state.gateway.connect(port):
                    st.session_state.gateway.start()
                    st.session_state.connected = True
                    st.success(f"Connected to {port}")
                else:
                    st.error("Connection failed")
            else:
                st.error("No ports available")
    
    with col2:
        if st.button("Disconnect", disabled=not st.session_state.connected):
            st.session_state.gateway.stop()
            st.session_state.connected = False
            st.info("Disconnected")
    
    # Connection status
    if st.session_state.connected:
        st.success("🟢 Connected")
        if st.session_state.last_update:
            elapsed = time.time() - st.session_state.last_update
            st.caption(f"Last update: {elapsed:.1f}s ago")
    else:
        st.error("🔴 Disconnected")
    
    st.divider()
    
    # Threshold settings
    st.subheader("Flow Thresholds")
    close_th = st.number_input("Close Threshold (L/min)", min_value=0, max_value=999, value=80, step=5)
    open_th = st.number_input("Open Threshold (L/min)", min_value=0, max_value=999, value=20, step=5)
    
    if st.button("Apply Thresholds", type="primary", disabled=not st.session_state.connected):
        if open_th <= close_th:
            def ack_callback(ack):
                if ack.get("ok"):
                    st.success(f"✅ {ack.get('msg', 'Success')}")
                else:
                    st.error(f"❌ {ack.get('msg', 'Failed')}")
            
            try:
                st.session_state.gateway.set_thresholds(close_th, open_th, ack_callback)
                st.info("Command sent, waiting for ACK...")
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.error("Open threshold must be <= Close threshold")
    
    st.divider()
    
    # Auto refresh
    st.session_state.auto_refresh = st.checkbox("Auto Refresh", value=True)
    refresh_interval = st.slider("Refresh Interval (s)", 1, 10, 2)


# ===== MAIN CONTENT =====

# Header
st.title("💧 Zigbee Flow Monitoring Dashboard")
st.caption(f"Real-time monitoring | Last update: {format_timestamp(st.session_state.last_update)}")

# Get current data
current_data = st.session_state.last_data
flow = current_data.get("flow", 0)
battery = current_data.get("battery", 0)
valve = current_data.get("valve", "unknown")

# ===== METRIC CARDS =====
col1, col2, col3 = st.columns(3)

with col1:
    # Flow card
    flow_status, flow_color = get_flow_status(flow, close_th, open_th)
    st.markdown(f"""
    <div style='background: linear-gradient(135deg, {flow_color}22 0%, {flow_color}44 100%); 
                padding: 20px; border-radius: 10px; border-left: 5px solid {flow_color}'>
        <div class='metric-label'>💧 Flow Rate</div>
        <div class='big-metric' style='color: {flow_color}'>{flow}</div>
        <div style='font-size: 14px; color: #666; margin-top: 5px'>L/min</div>
        <div style='margin-top: 10px'>
            <span class='status-badge' style='background-color: {flow_color}22; color: {flow_color}'>{flow_status}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    # Battery card
    battery_color = get_battery_color(battery)
    st.markdown(f"""
    <div style='background: linear-gradient(135deg, {battery_color}22 0%, {battery_color}44 100%); 
                padding: 20px; border-radius: 10px; border-left: 5px solid {battery_color}'>
        <div class='metric-label'>🔋 Battery Level</div>
        <div class='big-metric' style='color: {battery_color}'>{battery}</div>
        <div style='font-size: 14px; color: #666; margin-top: 5px'>%</div>
        <div style='margin-top: 10px; background-color: #f0f0f0; border-radius: 10px; height: 10px; overflow: hidden'>
            <div style='width: {battery}%; height: 100%; background-color: {battery_color}; transition: width 0.3s'></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    # Valve card
    valve_color = "#28a745" if valve == "open" else "#dc3545"
    valve_icon = "🟢" if valve == "open" else "🔴"
    st.markdown(f"""
    <div style='background: linear-gradient(135deg, {valve_color}22 0%, {valve_color}44 100%); 
                padding: 20px; border-radius: 10px; border-left: 5px solid {valve_color}'>
        <div class='metric-label'>🚰 Valve Status</div>
        <div style='font-size: 36px; font-weight: bold; color: {valve_color}; margin: 10px 0'>
            {valve_icon} {valve.upper()}
        </div>
        <div style='margin-top: 15px'>
    """, unsafe_allow_html=True)
    
    # Valve control buttons
    vcol1, vcol2 = st.columns(2)
    with vcol1:
        if st.button("🟢 OPEN", disabled=not st.session_state.connected or valve == "open", key="open_valve"):
            def ack_cb(ack):
                st.session_state.ack_status = ack
            try:
                st.session_state.gateway.set_valve("open", ack_cb)
            except Exception as e:
                st.error(f"Error: {e}")
    
    with vcol2:
        if st.button("🔴 CLOSE", disabled=not st.session_state.connected or valve == "closed", key="close_valve"):
            def ack_cb(ack):
                st.session_state.ack_status = ack
            try:
                st.session_state.gateway.set_valve("closed", ack_cb)
            except Exception as e:
                st.error(f"Error: {e}")
    
    st.markdown("</div></div>", unsafe_allow_html=True)

# ACK status
if st.session_state.ack_status:
    ack = st.session_state.ack_status
    if ack.get("ok"):
        st.success(f"✅ Command #{ack.get('id')}: {ack.get('msg', 'Success')}")
    else:
        st.error(f"❌ Command #{ack.get('id')}: {ack.get('msg', 'Failed')}")
    # Clear after showing
    if st.button("Clear"):
        st.session_state.ack_status = None
        st.rerun()

st.divider()

# ===== CHARTS =====
st.header("📊 Data Visualization")

# Chart tabs
tab1, tab2, tab3, tab4 = st.tabs(["📈 Live (5 min)", "⏱️ Hourly", "📅 Daily", "📆 Monthly"])

with tab1:
    st.subheader("Live Data (Last 5 minutes)")
    
    # Get recent data
    rows = st.session_state.gateway.get_telemetry_last_n(300)
    
    if rows:
        df = pd.DataFrame(rows, columns=['ts', 'flow', 'battery', 'valve'])
        df['time'] = pd.to_datetime(df['ts'], unit='s')
        
        # Create subplots
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=("Flow Rate (L/min)", "Battery Level (%)"),
            vertical_spacing=0.15,
            specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
        )
        
        # Flow chart
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['flow'], name="Flow", 
                      line=dict(color='#17a2b8', width=2),
                      fill='tozeroy', fillcolor='rgba(23,162,184,0.2)'),
            row=1, col=1
        )
        
        # Threshold lines
        fig.add_hline(y=close_th, line_dash="dash", line_color="red", 
                     annotation_text="Close Threshold", row=1, col=1)
        fig.add_hline(y=open_th, line_dash="dash", line_color="green", 
                     annotation_text="Open Threshold", row=1, col=1)
        
        # Battery chart
        fig.add_trace(
            go.Scatter(x=df['time'], y=df['battery'], name="Battery",
                      line=dict(color='#28a745', width=2),
                      fill='tozeroy', fillcolor='rgba(40,167,69,0.2)'),
            row=2, col=1
        )
        
        fig.update_layout(height=600, showlegend=False, hovermode='x unified')
        fig.update_xaxes(title_text="Time", row=2, col=1)
        fig.update_yaxes(title_text="L/min", row=1, col=1)
        fig.update_yaxes(title_text="%", row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Stats
        scol1, scol2, scol3, scol4 = st.columns(4)
        scol1.metric("Avg Flow", f"{df['flow'].mean():.1f} L/min")
        scol2.metric("Max Flow", f"{df['flow'].max():.1f} L/min")
        scol3.metric("Min Flow", f"{df['flow'].min():.1f} L/min")
        scol4.metric("Data Points", len(df))
    else:
        st.info("No data available. Connect to device to start collecting data.")

with tab2:
    st.subheader("Hourly Aggregated Data")
    
    rows = st.session_state.gateway.get_aggregated_data('hour', limit=24)
    
    if rows:
        df = pd.DataFrame(rows, columns=['ts', 'avg_flow', 'max_flow', 'min_flow', 'avg_battery'])
        df['time'] = pd.to_datetime(df['ts'], unit='s')
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['time'], y=df['avg_flow'], name="Avg Flow",
                                line=dict(color='#17a2b8', width=3)))
        fig.add_trace(go.Scatter(x=df['time'], y=df['max_flow'], name="Max Flow",
                                line=dict(color='#dc3545', width=2, dash='dot')))
        fig.add_trace(go.Scatter(x=df['time'], y=df['min_flow'], name="Min Flow",
                                line=dict(color='#28a745', width=2, dash='dot')))
        
        fig.update_layout(height=400, title="Flow Rate (L/min)", hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)
        
        # Battery
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df['time'], y=df['avg_battery'], name="Battery",
                                 line=dict(color='#28a745', width=3),
                                 fill='tozeroy'))
        fig2.update_layout(height=300, title="Battery Level (%)", hovermode='x unified')
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No aggregated data available yet.")

with tab3:
    st.subheader("Daily Aggregated Data")
    
    rows = st.session_state.gateway.get_aggregated_data('day', limit=30)
    
    if rows:
        df = pd.DataFrame(rows, columns=['ts', 'avg_flow', 'max_flow', 'min_flow', 'avg_battery'])
        df['time'] = pd.to_datetime(df['ts'], unit='s')
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df['time'], y=df['avg_flow'], name="Avg Flow",
                            marker_color='#17a2b8'))
        
        fig.update_layout(height=400, title="Daily Average Flow (L/min)", hovermode='x')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No daily data available yet.")

with tab4:
    st.subheader("Monthly View")
    st.info("Monthly aggregation - Coming soon!")

# Auto refresh
if st.session_state.auto_refresh and st.session_state.connected:
    time.sleep(refresh_interval)
    st.rerun()
