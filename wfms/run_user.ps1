# Run User Dashboard - Start the WFMS User Dashboard
#
# Purpose:
#   Launches the Streamlit user dashboard for WFMS monitoring and control.
#   Provides user-friendly interface for valve control and telemetry viewing.
#
# Usage:
#   .\run_user.ps1
#
# Requirements:
#   - Python 3.11+
#   - streamlit installed (see requirements.txt)
#   - MQTT broker running
#
# Default Port: 8502

Set-Location "$PSScriptRoot"
streamlit run dashboards/user/user_dashboard.py --server.port 8502
