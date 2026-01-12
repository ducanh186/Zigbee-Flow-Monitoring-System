# MQTT Commands Reference

**Hướng dẫn điều khiển valve và mode qua MQTT**

---

## 📡 MQTT Broker Configuration

| Parameter | Value |
|-----------|-------|
| Host | `26.172.222.181` |
| Port | `1883` |
| Protocol | MQTT v3.1.1 |

---

## 🎮 Mode Commands (Auto/Manual Toggle)

### **Chuyển sang Manual Mode**

Bắt buộc trước khi điều khiển valve từ xa.

**PowerShell:**
```powershell
echo '{"cid":"mode_manual","value":"manual"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/mode' -l
```

**CMD:**
```cmd
mosquitto_pub -h 26.172.222.181 -t "wfms/lab1/cmd/mode" -m "{\"cid\":\"mode_manual\",\"value\":\"manual\"}"
```

**Không cần cid (auto-generate):**
```powershell
echo '{"value":"manual"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/mode' -l
```

---

### **Chuyển sang Auto Mode**

Valve sẽ tự động điều khiển theo flow threshold.

**PowerShell:**
```powershell
echo '{"cid":"mode_auto","value":"auto"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/mode' -l
```

**CMD:**
```cmd
mosquitto_pub -h 26.172.222.181 -t "wfms/lab1/cmd/mode" -m "{\"cid\":\"mode_auto\",\"value\":\"auto\"}"
```

---

## 🔧 Valve Commands (ON/OFF Toggle)

### **Bật Valve (ON)**

**PowerShell:**
```powershell
echo '{"cid":"valve_on","value":"ON"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/valve' -l
```

**CMD:**
```cmd
mosquitto_pub -h 26.172.222.181 -t "wfms/lab1/cmd/valve" -m "{\"cid\":\"valve_on\",\"value\":\"ON\"}"
```

**Không cần cid (auto-generate):**
```powershell
echo '{"value":"ON"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/valve' -l
```

---

### **Tắt Valve (OFF)**

**PowerShell:**
```powershell
echo '{"cid":"valve_off","value":"OFF"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/valve' -l
```

**CMD:**
```cmd
mosquitto_pub -h 26.172.222.181 -t "wfms/lab1/cmd/valve" -m "{\"cid\":\"valve_off\",\"value\":\"OFF\"}"
```

---

## 📊 Subscribe to Responses

### **Monitor ACK (Acknowledgment)**

```powershell
mosquitto_sub -h 26.172.222.181 -t 'wfms/lab1/ack' -v
```

**Expected Response:**
```json
wfms/lab1/ack {"cid":"valve_on","ok":true,"reason":"","ts":1736672944}
```

---

### **Monitor State (Retained)**

```powershell
mosquitto_sub -h 26.172.222.181 -t 'wfms/lab1/state' -v
```

**Expected Response:**
```json
wfms/lab1/state {
  "flow": 55,
  "battery": 93,
  "valve": "ON",
  "mode": "manual",
  "valvePath": "binding",
  "valveKnown": true,
  "valveNodeId": "0x1D34",
  "txPending": false,
  "updatedAt": 1736672944
}
```

---

### **Monitor All Topics**

```powershell
mosquitto_sub -h 26.172.222.181 -t 'wfms/lab1/#' -v
```

---

## 🧪 Full Test Sequence

**Terminal 1: Start Gateway**
```powershell
cd D:\CODE\Zigbee-Flow-Monitoring-System\wfms
python -m gateway.service
```

**Terminal 2: Monitor Responses**
```powershell
mosquitto_sub -h 26.172.222.181 -t 'wfms/lab1/#' -v
```

**Terminal 3: Send Commands**
```powershell
# Step 1: Chuyển sang manual mode
echo '{"value":"manual"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/mode' -l

# Wait 1-2 seconds
Start-Sleep -Seconds 2

# Step 2: Bật valve
echo '{"value":"ON"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/valve' -l

# Wait 2 seconds
Start-Sleep -Seconds 2

# Step 3: Tắt valve
echo '{"value":"OFF"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/valve' -l

# Wait 2 seconds
Start-Sleep -Seconds 2

# Step 4: Chuyển về auto mode
echo '{"value":"auto"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/mode' -l
```

---

## 📝 Command Payload Format

### **Mode Command**

| Field | Required | Type | Values | Description |
|-------|----------|------|--------|-------------|
| `cid` | No | string | Any unique ID | Auto-generated if missing |
| `value` | **Yes** | string | `auto`, `manual` | Target mode |
| `by` | No | string | Username | Who sent command |

**Example:**
```json
{
  "cid": "mode_cmd_123",
  "value": "manual",
  "by": "admin"
}
```

---

### **Valve Command**

| Field | Required | Type | Values | Description |
|-------|----------|------|--------|-------------|
| `cid` | No | string | Any unique ID | Auto-generated if missing |
| `value` | **Yes** | string | `ON`, `OFF` | Target valve state |
| `by` | No | string | Username | Who sent command |

**Example:**
```json
{
  "cid": "valve_cmd_456",
  "value": "ON",
  "by": "admin"
}
```

---

## 🚨 Common Issues

### **1. PowerShell Quote Escaping Error**

**Error:**
```
Error: Unknown option 'cid\:\valve_on\,\value\:\ON\}'
```

**Solution:** Dùng single quotes hoặc echo + pipe
```powershell
# ✅ ĐÚNG: Single quotes
mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/valve' -m '{"value":"ON"}'

# ✅ ĐÚNG: Echo + pipe
echo '{"value":"ON"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/valve' -l

# ❌ SAI: Double quotes trong PowerShell
mosquitto_pub -h 26.172.222.181 -t "wfms/lab1/cmd/valve" -m "{\"value\":\"ON\"}"
```

---

### **2. Valve Command Rejected (Auto Mode)**

**Error ACK:**
```json
{"cid":"valve_123","ok":false,"reason":"rejected: AUTO mode"}
```

**Solution:** Chuyển sang manual mode trước:
```powershell
echo '{"value":"manual"}' | mosquitto_pub -h 26.172.222.181 -t 'wfms/lab1/cmd/mode' -l
```

---

### **3. ACK Timeout**

**Gateway Log:**
```
WARNING - ACK timeout for cid=valve_123 after retries
```

**Possible Causes:**
- Gateway mode chưa bật trên Coordinator: `json {"id":1,"op":"uart_gateway_set","enable":true}`
- COM port bị chiếm bởi Simplicity Console
- UART cable không kết nối

**Solution:**
```bash
# Trên Simplicity Console, bật gateway mode:
json {"id":1,"op":"uart_gateway_set","enable":true}
```

---

## 🔗 Related Documentation

- [Gateway Service README](../wfms/README.md)
- [MQTT Broker Setup](../README.md#mqtt-broker-setup)
- [Protocol Specification](../wfms/common/proto.py)
- [Test Scripts](../tests/smoke/)

---

## 📞 Support

- **GitHub Issues:** [Project Repository](https://github.com/your-org/zigbee-flow-monitoring)
- **Documentation:** `D:\CODE\Zigbee-Flow-Monitoring-System\docs\`
- **Logs:** Gateway logs at `D:\CODE\Zigbee-Flow-Monitoring-System\wfms\gateway.log`

---

**Last Updated:** January 12, 2026
