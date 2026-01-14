import streamlit as st

def inject_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
        
        /* Hide Streamlit defaults */
        #MainMenu, footer {visibility: hidden;}
        
        /* Hide decoration bar but KEEP HEADER VISIBLE for the sidebar toggle */
        [data-testid="stDecoration"] {display: none;}
        [data-testid="stHeader"] {
            background: transparent;
            border-bottom: none;
        }

        .block-container { padding: 1rem 1rem 0 1rem !important; max-width: 100% !important; }
        
        /* ALWAYS show sidebar collapse/expand arrow button */
        section[data-testid="stSidebar"] > div {
            padding-top: 2rem;
        }
        
        [data-testid="collapsedControl"] {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            visibility: visible !important;
            opacity: 1 !important;
            color: #FFFFFF !important;
            z-index: 1000000 !important;
            background-color: #262730 !important;
            border-radius: 8px !important;
            padding: 6px !important;
            position: fixed !important;
            left: 1rem !important;
            top: 0.8rem !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
            transition: all 0.2s ease;
            width: 36px !important;  /* Ensure clickable area */
            height: 36px !important;
        }

        /* Ensure default icon is hidden if we want to add our own, 
           or style it if we want to keep it. The user said "Add icon". 
           Let's replace the default chevron with a menu (hamburger) icon using ::before 
           and hiding the original svg.
        */
        
        [data-testid="collapsedControl"] svg {
            display: none !important; /* Hide default chevron */
        }
        
        [data-testid="collapsedControl"]::before {
            content: "";
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23FFFFFF' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='3' y1='12' x2='21' y2='12'%3E%3C/line%3E%3Cline x1='3' y1='6' x2='21' y2='6'%3E%3C/line%3E%3Cline x1='3' y1='18' x2='21' y2='18'%3E%3C/line%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: center;
            width: 20px;
            height: 20px;
            display: block;
        }

        [data-testid="collapsedControl"]:hover {
            background-color: #383942 !important;
            border-color: rgba(255,255,255,0.3) !important;
        }
        
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
