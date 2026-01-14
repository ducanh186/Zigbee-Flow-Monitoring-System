# WFMS User Dashboard

Modular Streamlit dashboard for end-users to monitor flow rates and control valves.

## 🚀 How to Run

From the project root directory:

```powershell
python -m streamlit run wfms/dashboards/user/user_dashboard.py
```

## 📂 File Structure

| File | Purpose |
|------|---------|
| **`user_dashboard.py`** | **Controller**: Main entry point. Handles MQTT connection, state management, and app lifecycle. |
| **`views.py`** | **View**: Contains UI rendering logic (Header, Charts, Valve Status Card, Control Panel). |
| **`styles.py`** | **Styles**: Manages Custom CSS injection for the dark theme and layout adjustments. |
| **`utils.py`** | **Utils**: Handles configuration loading (`.env`), helper functions (time formatting), and session state init. |
