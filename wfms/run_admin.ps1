# Run Admin Dashboard - Start the WFMS Admin Dashboard
#
# Purpose:
#   Launches the Streamlit admin dashboard for WFMS system management.
#   Provides access to live telemetry, network settings, and system logs.
#
# Usage:
#   .\run_admin.ps1
#
# Requirements:
#   - Python 3.11+
#   - streamlit installed (see requirements.txt)
#   - MQTT broker running
#
# Default Port: 8501

Set-Location "$PSScriptRoot"
streamlit run dashboards/admin/admin_dashboard.py --server.port 8501
