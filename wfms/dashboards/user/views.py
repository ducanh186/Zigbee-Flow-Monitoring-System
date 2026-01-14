import time
import pandas as pd
import streamlit as st
from datetime import datetime
import json

# Try relative/absolute imports for utils
try:
    import utils
except ImportError:
    from . import utils

# Optional imports
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# =============================================================================
# Helper Rendering Functions
# =============================================================================

def render_header(connected, mqtt_host, packet_count, site):
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
                <p class="header-subtitle">Site: {site.upper()}</p>
            </div>
        </div>
        <div class="header-stats">
            <div class="status-online">
                <div class="status-dot"></div>
                <span>{'ONLINE' if connected else 'OFFLINE'}</span>
            </div>
            <div class="broker-info">
                Broker: <span>{mqtt_host}</span>
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

def render_chart(mqtt_mgr):
    with st.container():
        st.markdown("""
        <div class="chart-header">
            <span class="chart-title">📈 Flow History</span>
        </div>
        """, unsafe_allow_html=True)
        
        # Time window selector
        tw_cols = st.columns([1, 1, 1, 6])
        current_window = st.session_state.get('time_window', 'Live')
        
        with tw_cols[0]:
            if st.button("Live", key="tw_live", type="primary" if current_window == "Live" else "secondary"):
                st.session_state.time_window = "Live"
        with tw_cols[1]:
            if st.button("15m", key="tw_15m", type="primary" if current_window == "15m" else "secondary"):
                st.session_state.time_window = "15m"
        with tw_cols[2]:
            if st.button("1h", key="tw_1h", type="primary" if current_window == "1h" else "secondary"):
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
                    # Ensure received_at is used for time
                    if 'received_at' in df.columns:
                        df['time'] = pd.to_datetime(df['received_at'].apply(datetime.fromtimestamp))
                    else:
                        df['time'] = pd.to_datetime(df['ts'].apply(datetime.fromtimestamp))
                        
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
                    st.info("Waiting for flow metrics...")
            else:
                st.info("No data in selected window")
        else:
            # Placeholder
            st.info("📊 Waiting for telemetry data...")

def render_logs_and_health(mqtt_mgr):
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
        uptime = gateway.get('uptime', '4d 12h') if gateway else 'Unknown'
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

def render_valve_card(is_open, latest_flow, latest_battery):
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

def render_controls(mqtt_mgr, site):
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    
    # CONTROL PANEL HEADER
    st.markdown("""
    <div class="valve-card" style="width: 80%; margin: 0 auto;">
        <div style="display:flex;justify-content:center;align-items:center;margin-bottom:16px;">
             <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FAFAFA" stroke-width="2" style="margin-right: 8px;">
                <path d="M12 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4z"/>
                <path d="M5 22h14v-4a2 2 0 0 0-2-2h-3v-4h3l-1-7h-8l-1 7h3v4h-3a2 2 0 0 0-2 2v4z"/>
             </svg>
            <span style="font-weight:700;font-size:15px;color:#FAFAFA;">CONTROLS</span>
        </div>
    """, unsafe_allow_html=True)
    
    # Mode toggle
    current_mode = st.session_state.get('current_mode', 'AUTO')
    mode_cols = st.columns(2)
    with mode_cols[0]:
        if st.button("🤖 AUTO", key="mode_auto", type="primary" if current_mode == "AUTO" else "secondary"):
            if current_mode != "AUTO":
                mqtt_mgr.publish(f"wfms/{site}/cmd/mode", {
                    "cid": f"user_{int(time.time()*1000)}",
                    "value": "AUTO",
                    "by": "user_dashboard",
                    "ts": int(time.time())
                })
                st.session_state.current_mode = "AUTO"
                utils.add_log("Switched to AUTO mode", "info")
                st.rerun()
    with mode_cols[1]:
        if st.button("✋ MANUAL", key="mode_manual", type="primary" if current_mode == "MANUAL" else "secondary"):
            if current_mode != "MANUAL":
                mqtt_mgr.publish(f"wfms/{site}/cmd/mode", {
                    "cid": f"user_{int(time.time()*1000)}",
                    "value": "MANUAL",
                    "by": "user_dashboard",
                    "ts": int(time.time())
                })
                st.session_state.current_mode = "MANUAL"
                utils.add_log("Switched to MANUAL mode", "warn")
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
                success, error = mqtt_mgr.publish(f"wfms/{site}/cmd/valve", {
                    "cid": f"user_{int(time.time()*1000)}",
                    "value": "ON",
                    "by": "user_dashboard",
                    "ts": int(time.time())
                })
                if success:
                    utils.add_log("Command sent: OPEN VALVE", "success")
                else:
                    utils.add_log(f"Failed: {error}", "error")
                st.rerun()
        with btn_cols[1]:
            if st.button("🔴 CLOSE", key="valve_close", use_container_width=True):
                success, error = mqtt_mgr.publish(f"wfms/{site}/cmd/valve", {
                    "cid": f"user_{int(time.time()*1000)}",
                    "value": "OFF",
                    "by": "user_dashboard",
                    "ts": int(time.time())
                })
                if success:
                    utils.add_log("Command sent: CLOSE VALVE", "error")
                else:
                    utils.add_log(f"Failed: {error}", "error")
                st.rerun()
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_command_history(mqtt_mgr):
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    st.markdown('<p class="section-header">📜 Recent Commands</p>', unsafe_allow_html=True)
    
    cmds = mqtt_mgr.get_commands(5)
    if cmds:
        cmd_html = '<div style="max-height:120px;overflow-y:auto;">'
        for cmd in cmds:
            cmd_time = utils.format_time_short(cmd.get('sent_at'))
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
# MAIN RENDER ENTRY POINT
# =============================================================================

def render_dashboard(mqtt_mgr):
    stats = mqtt_mgr.get_stats()
    state = mqtt_mgr.get_state()
    
    # Get configuration from utils
    is_connected = stats['connected']
    mqtt_host = utils.MQTT_HOST
    site = utils.SITE
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
    
    # 1. Header
    render_header(is_connected, mqtt_host, packet_count, site)
    
    # 2. Main Grid
    col_left, col_right = st.columns([2, 1], gap="medium")
    
    with col_left:
        render_chart(mqtt_mgr)
        render_logs_and_health(mqtt_mgr)
        
    with col_right:
        render_valve_card(is_open, latest_flow, latest_battery)
        render_controls(mqtt_mgr, site)
        render_command_history(mqtt_mgr)
