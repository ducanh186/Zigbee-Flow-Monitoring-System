# Setup Scripts

One-time initialization scripts for configuring the development environment.

## Scripts

### 1. `setup_mosquitto_lan.ps1` - **Run FIRST**
Initializes Mosquitto broker for LAN development.

**What it does:**
- Checks Mosquitto installation
- Creates persistence directory (`mosquitto_data/`)
- Configures Windows Firewall (opens port 1883)
- Shows network information
- Checks if port 1883 is already in use

**Usage:**
```powershell
# Run as Administrator
.\setup_mosquitto_lan.ps1
```

**Prerequisites:**
- Mosquitto installed at `C:\Program Files\mosquitto\`
- Run as **Administrator**

**Output:**
```
Local IP: 192.168.1.100
MQTT URL: mqtt://192.168.1.100:1883
```

---

### 2. `setup_firewall.ps1` - **For Streamlit Dashboard (Optional)**
Configures Windows Firewall for Streamlit dashboard port 8502.

**What it does:**
- Removes old firewall rule if exists
- Adds rule for TCP port 8502
- Shows accessible URLs
- Checks if port is listening

**Usage:**
```powershell
# Run as Administrator
.\setup_firewall.ps1
```

**Prerequisites:**
- Run as **Administrator**

---

## Setup Workflow

1. **First time setup:**
   ```powershell
   cd tools\setup
   .\setup_mosquitto_lan.ps1      # Setup broker + firewall
   # .\setup_firewall.ps1           # Optional: for dashboard
   ```

2. **Then start broker:**
   ```powershell
   cd tools\mqtt
   .\start_broker.ps1
   ```

3. **Run gateway:**
   ```powershell
   cd wfms
   python -m gateway.service
   ```

---

## Troubleshooting

### "Mosquitto not found"
- Install Mosquitto: https://mosquitto.org/download/
- Ensure it's in `C:\Program Files\mosquitto\`

### "Run as Administrator" error
- Right-click PowerShell → "Run as Administrator"
- Or use: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### Port 1883 already in use
- Script will detect and offer to kill the process
- Or manually: `netstat -ano | findstr :1883`

### Can't connect from remote machine
- Verify firewall rule: `netsh advfirewall firewall show rule name="Mosquitto MQTT Broker (TCP 1883)"`
- Check `mosquitto.conf` has: `listener 1883 0.0.0.0`
