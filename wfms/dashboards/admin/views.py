import time
import pandas as pd
import streamlit as st
import datetime

try:
    import utils
except ImportError:
    from . import utils

# Optional imports
try:
    import plotly.express as px
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
# SIDEBAR
# =============================================================================

def render_sidebar(mqtt_mgr):
    config = utils.get_config()
    stats = mqtt_mgr.get_stats()
    
    with st.sidebar:
        st.markdown("## 🚰 WFMS Admin")
        st.caption(f"Site: **{config['site']}**")
        st.divider()
        
        if OPTION_MENU_AVAILABLE:
            pages = ["Live View", "Network Setting", "System Logs"]
            icons = ["activity", "wifi", "file-text"]
            
            # Helper logic to determine default index
            current = st.session_state.current_page
            idx = 0
            if current in pages:
                idx = pages.index(current)
                
            selected = option_menu(
                menu_title=None,
                options=pages,
                icons=icons,
                default_index=idx,
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
                    st.markdown(f"**{label}**")
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
            st.caption(f"Last: {utils.format_ago(stats['last_message_time'])}")
        
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

def render_live_view(mqtt_mgr):
    stats = mqtt_mgr.get_stats()
    state = mqtt_mgr.get_state()
    config = utils.get_config()
    
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
    # MAIN GRID
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
                if st.button("Live", key="tw_live", type="primary" if st.session_state.time_window=="Live" else "secondary"):
                    st.session_state.time_window = "Live"
                    st.rerun()
            with tw_cols[1]:
                if st.button("1H", key="tw_1h", type="primary" if st.session_state.time_window=="1H" else "secondary"):
                    st.session_state.time_window = "1H"
                    st.rerun()
            with tw_cols[2]:
                if st.button("24H", key="tw_24h", type="primary" if st.session_state.time_window=="24H" else "secondary"):
                    st.session_state.time_window = "24H"
                    st.rerun()
            
            # Get flow data
            flow_data = mqtt_mgr.get_flow_history(200)
            
            if flow_data and len(flow_data) > 0 and PLOTLY_AVAILABLE:
                df = pd.DataFrame(flow_data)
                df['color'] = '#29b5e8'
                
                # Filter by window (simplified logis as history might be short)
                # In real app, you filter df['ts'] against time.time() - window
                
                fig = px.area(df, x='time', y='flow', 
                              labels={'time': 'Time', 'flow': 'Flow (L/m)'},
                              template='plotly_dark')
                
                fig.update_traces(line_color='#29b5e8', fillcolor='rgba(41, 181, 232, 0.1)')
                fig.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0),
                    height=280,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
                    xaxis=dict(showgrid=False)
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No flow data available or Plotly not installed")
        
        # BOTTOM: Logs + Gateway Health
        log_col, gw_col = st.columns([2, 1])
        
        with log_col:
            st.markdown('<p class="section-header">System Logs</p>', unsafe_allow_html=True)
            
            # Build log HTML
            log_html = '<div class="log-panel custom-scrollbar">'
            for log in st.session_state.get('logs', [])[:15]:
                c = "log-info"
                if log['type'] == 'success': c = "log-success"
                elif log['type'] == 'error': c = "log-error"
                elif log['type'] == 'warning': c = "log-warn"
                
                log_html += f'<div class="log-entry"><span class="log-time">[{log["time"]}]</span> <span class="{c}">{log["message"]}</span></div>'
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
        # width: 60%  -> Make it shorter horizontally
        # margin: 0 auto -> Center the whole box content (if parent is flex) or just visually center
        # text-align: center -> Center "Controls" text
        
        st.markdown("""
        <div class="valve-card" style="width:60% margin: 0 auto;">
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
        if state and isinstance(state, dict) and 'mode' in state:
            current_mode = state.get('mode', 'AUTO').upper()
            st.session_state.current_mode = current_mode
        
        mode_cols = st.columns(2)
        with mode_cols[0]:
            if st.button("🤖 AUTO", key="mode_auto", type="primary" if current_mode == "AUTO" else "secondary", use_container_width=True):
                utils.add_log("Switching to AUTO mode...", "info")
                mqtt_mgr.publish(f"wfms/{config['site']}/cmd/valve", {"mode": "auto"})
                
        with mode_cols[1]:
            if st.button("✋ MANUAL", key="mode_manual", type="primary" if current_mode == "MANUAL" else "secondary", use_container_width=True):
                utils.add_log("Switching to MANUAL mode...", "info")
                mqtt_mgr.publish(f"wfms/{config['site']}/cmd/valve", {"mode": "manual"})
        
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
                if st.button("🌊 OPEN VALVE", key="btn_open", type="primary" if not is_open else "secondary", use_container_width=True):
                    utils.add_log("Sending Command: OPEN VALVE", "info")
                    mqtt_mgr.publish(f"wfms/{config['site']}/cmd/valve", {"value": "ON"})
            with btn_cols[1]:
                if st.button("🔒 CLOSE VALVE", key="btn_close", type="primary" if is_open else "secondary", use_container_width=True):
                    utils.add_log("Sending Command: CLOSE VALVE", "info")
                    mqtt_mgr.publish(f"wfms/{config['site']}/cmd/valve", {"value": "OFF"})
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        
        # COMMAND HISTORY
        st.markdown('<p class="section-header">📜 Recent Commands</p>', unsafe_allow_html=True)
        
        cmds = mqtt_mgr.get_commands(5)
        if cmds:
            cmd_html = '<div style="max-height:120px;overflow-y:auto;">'
            for cmd in cmds:
                val = cmd.get('value') or cmd.get('mode') or 'UNK'
                cmd_html += f'''
                <div class="cmd-entry">
                    <div>
                        <div class="cmd-action">{val.upper()}</div>
                        <div class="cmd-source">{cmd.get('topic','').split('/')[-1]}</div>
                    </div>
                    <div class="cmd-time">{utils.format_time_short(cmd.get('sent_at'))}</div>
                </div>
                '''
            cmd_html += '</div>'
            st.markdown(cmd_html, unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#6B7280;font-size:12px;text-align:center;">No commands sent yet</p>', unsafe_allow_html=True)


# =============================================================================
# NETWORK SETTING
# =============================================================================

def render_network_setting(mqtt_mgr):
    st.header("🌐 Network Setting")
    config = utils.get_config()
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
            st.session_state.config_applied_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # CALL RECONNECT via manager
            mqtt_mgr.reconnect(st.session_state.config)
            
            utils.add_log(f"Network config updated: {new_mqtt_host}:{new_mqtt_port}", "success")
            st.success("✅ Configuration applied!")
            time.sleep(1)
            st.rerun()
    
    with c2:
        if st.button("🔄 Reset to Default"):
            st.session_state.config = utils.DEFAULT_CONFIG.copy()
            mqtt_mgr.reconnect(st.session_state.config)
            utils.add_log("Network config reset to default", "info")
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
        st.metric("Last Message", utils.format_ago(stats['last_message_time']))
    with c4:
        st.metric("Errors", stats['parse_error_count'])


# =============================================================================
# SYSTEM LOGS
# =============================================================================

def render_system_logs(mqtt_mgr):
    st.header("📋 System Logs & Debug Data")
    
    stats = mqtt_mgr.get_stats()
    config = utils.get_config()
    
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
                st.rerun()
        
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
            ok, data, err = utils.api_get(f"/logs?tail={tail}")
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
                st.info("No API logs")
    
    # --- TELEMETRY DATA ---
    with tab_telemetry:
        st.subheader("📡 Raw Telemetry History")
        tele = mqtt_mgr.get_telemetry(50)
        if tele:
            st.dataframe([{
                "Time": utils.format_time_short(t.get('ts') or t.get('received_at')),
                "Flow": f"{t.get('flow', 0):.2f}",
                "Battery": f"{t.get('battery', '--')}%",
                "Valve": t.get('valve', '--')
            } for t in tele], hide_index=True)
            
            with st.expander("📋 Raw JSON Data"):
                st.write(tele)
        else:
            st.info("No telemetry data yet...")
    
    # --- ACK RESPONSES ---
    with tab_acks:
        st.subheader("✅ ACK Responses from Gateway")
        acks = mqtt_mgr.get_acks(50)
        if acks:
            log_lines = []
            for a in acks:
                log_lines.append(f"{utils.format_time_short(a.get('ts'))} CID={a.get('cid','?')} OK={a.get('ok')} {a.get('msg','')}")
            st.code("\n".join(log_lines), language="text")
            
            with st.expander("📋 Raw JSON Data"):
                st.write(acks)
        else:
            st.info("No ACK responses yet...")
    
    # --- COMMAND HISTORY ---
    with tab_commands:
        st.subheader("📤 Sent Commands History")
        cmds = mqtt_mgr.get_commands(50)
        if cmds:
            st.dataframe([{
                "Time": utils.format_time_short(c.get('sent_at')),
                "CID": c.get('cid', '--'),
                "Value": c.get('value', '--'),
                "Topic": c.get('topic', '--').split('/')[-1]
            } for c in cmds], hide_index=True)
            
            with st.expander("📋 Raw JSON Data"):
                st.write(cmds)
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
            "last_message": utils.format_ago(stats['last_message_time']),
            "connect_time": utils.format_timestamp(stats['connect_time']),
            "last_error": stats['last_error']
        })
        
        # Current Config
        st.markdown("#### Current Configuration")
        st.json(config)
