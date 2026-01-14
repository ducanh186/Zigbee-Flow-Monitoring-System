# WFMS Admin Dashboard

## 🚀 How to Run

You can start the dashboard using the provided PowerShell script or directly via Streamlit.

**From the `wfms` directory:**

```powershell
# Option 1: Using the helper script (Recommended)
.\run_admin.ps1

# Option 2: Direct Streamlit command
streamlit run dashboards/admin/admin_dashboard.py
```

---

## 📂 File Structure & Purpose

The dashboard logic is separated into four modules for better maintainability:

### 1. `admin_dashboard.py` (Controller)
*   **Role**: Main Entry Point & Logic Core.
*   **Details**: Initializes the application, manages the **MQTT connection** (subscriptions, publishing), updates Session State, and calls views to render.

### 2. `views.py` (User Interface)
*   **Role**: Presentation Layer.
*   **Details**: Contains functions to render specific pages (`render_live_view`, `render_network_setting`, `render_system_logs`). It receives data from the controller and displays it.

### 3. `styles.py` (Styling)
*   **Role**: CSS & Theming.
*   **Details**: Injects raw CSS to override Streamlit defaults. Handles the custom dark theme, sidebar toggle button hacks, and component styling (cards, badges).

### 4. `utils.py` (Utilities)
*   **Role**: Helpers & Configuration.
*   **Details**: Shared helper functions for:
    *   Loading configuration (from `.env`).
    *   Formatting time and strings.
    *   Handling HTTP API requests.
    *   Managing session state initialization.
