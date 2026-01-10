# 🚀 WFMS Gateway - Hướng dẫn cho UI Developer

**Dành cho**: Person B (UI/Dashboard Developer)  
**Mục đích**: Test dashboard mà KHÔNG CẦN phần cứng Zigbee

---

## ⚡ Quick Start (3 Bước)

### 1️⃣ Khởi động Gateway Fake UART

```powershell
cd wfms
python -m gateway.service --fake-uart
```

**Hoặc double-click**: `run_fake.ps1` (nếu có)

Bạn sẽ thấy:
```
==================================================
   FAKE UART MODE (for UI development)
   Drop ACK probability: 0.0
==================================================
WFMS Gateway Service Starting
...
✓ MQTT connected
✓ Subscribed to wfms/lab1/cmd/valve
```

### 2️⃣ Xem dữ liệu real-time

**Mở terminal mới**, chạy:

```powershell
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -t "wfms/lab1/#" -v
```

Bạn sẽ thấy data mỗi giây:
```
wfms/lab1/telemetry {"flow": 12.5, "battery": 85, "ts": 1768031400}
wfms/lab1/state {"flow": 12.5, "battery": 85, "valve": "OFF", "updatedAt": 1768031400}
```

### 3️⃣ Test điều khiển van

**Bật van:**
```powershell
echo '{"cid":"test_on","value":"ON","by":"ui_dev","ts":1768031400}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l
```

**Tắt van:**
```powershell
echo '{"cid":"test_off","value":"OFF","by":"ui_dev","ts":1768031401}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l
```

Sau mỗi lệnh, bạn sẽ nhận được ACK:
```
wfms/lab1/ack {"cid":"test_on","ok":true,"reason":"","ts":1768031400}
```

---

## 📡 MQTT Topics (Contract)

**QUAN TRỌNG**: Đây là contract cố định, KHÔNG được thay đổi!

### Topics để SUBSCRIBE (nhận data từ Gateway)

| Topic | Retained | Mô tả | Payload mẫu |
|-------|----------|-------|-------------|
| `wfms/lab1/state` | ✅ | Trạng thái hiện tại | `{"flow":12.5,"battery":85,"valve":"ON","updatedAt":1768031400}` |
| `wfms/lab1/telemetry` | ❌ | Telemetry real-time | `{"flow":12.5,"battery":85,"ts":1768031400}` |
| `wfms/lab1/ack` | ❌ | ACK sau mỗi command | `{"cid":"xxx","ok":true,"reason":"","ts":1768031400}` |
| `wfms/lab1/status/gateway` | ✅ | Gateway online/offline | `{"up":true,"ts":1768031400}` |

### Topics để PUBLISH (gửi lệnh tới Gateway)

| Topic | Payload format | Mô tả |
|-------|----------------|-------|
| `wfms/lab1/cmd/valve` | `{"cid":"<unique>","value":"ON\|OFF","by":"<userId>","ts":<unix>}` | Lệnh điều khiển van |

---

## 🔧 Payload Format (JSON)

### Command (gửi từ Dashboard)

```json
{
  "cid": "cmd_20260110_001",      // Command ID duy nhất (bắt buộc)
  "value": "ON",                  // "ON" hoặc "OFF" (bắt buộc)
  "by": "admin_user",             // User ID (khuyên dùng)
  "ts": 1768031400                // Unix timestamp (khuyên dùng)
}
```

**Lưu ý CID**: 
- Phải unique cho mỗi command
- Duplicate CID trong 60s sẽ bị reject với `reason: "duplicate_cid"`

### ACK (nhận từ Gateway)

```json
{
  "cid": "cmd_20260110_001",      // Trùng với command CID
  "ok": true,                     // true = thành công, false = thất bại
  "reason": "",                   // Rỗng nếu ok=true, hoặc mã lỗi
  "ts": 1768031400                // Unix timestamp
}
```

**ACK Reasons** (khi `ok: false`):

| Reason | Ý nghĩa | UI nên làm gì |
|--------|---------|---------------|
| `locked` | Hệ thống đang lock | Hiển thị "System locked" |
| `duplicate_cid` | Command ID trùng | Generate CID mới |
| `cooldown_user` | User spam quá nhanh | Báo "Please wait X seconds" |
| `cooldown_global` | Hệ thống busy | Thử lại sau 1-2s |
| `missing_cid` | Thiếu CID | Fix bug UI |
| `invalid_value` | value không phải ON/OFF | Fix bug UI |
| `timeout` | Không nhận ACK từ coordinator | Báo lỗi kết nối |

### State (retained)

```json
{
  "flow": 12.5,                   // L/min (float)
  "battery": 85,                  // 0-100% (int)
  "valve": "ON",                  // "ON" hoặc "OFF"
  "updatedAt": 1768031400         // Unix timestamp
}
```

### Telemetry (real-time, không retained)

```json
{
  "flow": 12.5,                   // L/min
  "battery": 85,                  // 0-100%
  "ts": 1768031400                // Unix timestamp
}
```

---

## 🧪 Test Scenarios

### Scenario 1: Bật van, đợi ACK, kiểm tra state

```powershell
# 1. Subscribe để xem response
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -t "wfms/lab1/#" -v

# 2. Gửi ON command (terminal khác)
echo '{"cid":"sc1_on","value":"ON","by":"tester","ts":1768031400}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l

# 3. Xem ACK: ok=true, reason=""
# 4. Xem state: valve="ON", flow tăng (10-25 L/min)
```

### Scenario 2: Test duplicate CID (sẽ bị reject)

```powershell
# Gửi lần 1
echo '{"cid":"dup_test","value":"ON","by":"tester","ts":1}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l

# Gửi lại lần 2 với cùng CID (trong vòng 60s)
echo '{"cid":"dup_test","value":"OFF","by":"tester","ts":2}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l

# ACK lần 2: ok=false, reason="duplicate_cid"
```

### Scenario 3: Test cooldown (spam protection)

```powershell
# Gửi 3 commands liên tục từ cùng user
echo '{"cid":"cd1","value":"ON","by":"user1","ts":1}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l

echo '{"cid":"cd2","value":"OFF","by":"user1","ts":2}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l

echo '{"cid":"cd3","value":"ON","by":"user1","ts":3}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l

# Command thứ 2, 3 sẽ bị reject: reason="cooldown_user" hoặc "cooldown_global"
```

### Scenario 4: Test timeout (drop ACK)

```powershell
# Khởi động gateway với 50% drop ACK
python -m gateway.service --fake-uart --drop-ack-prob 0.5

# Gửi vài commands
echo '{"cid":"t1","value":"ON","by":"tester","ts":1}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l
echo '{"cid":"t2","value":"OFF","by":"tester","ts":2}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l
echo '{"cid":"t3","value":"ON","by":"tester","ts":3}' | & "C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -t "wfms/lab1/cmd/valve" -l

# ~50% commands sẽ timeout: ok=false, reason="timeout"
```

---

## 🐍 Python MQTT Client (cho Dashboard code)

### Cài thư viện

```bash
pip install paho-mqtt==1.6.1
```

### Subscribe example

```python
import paho.mqtt.client as mqtt
import json

def on_connect(client, userdata, flags, rc):
    print(f"Connected: {rc}")
    client.subscribe("wfms/lab1/state", qos=1)
    client.subscribe("wfms/lab1/telemetry", qos=0)
    client.subscribe("wfms/lab1/ack", qos=1)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = json.loads(msg.payload.decode())
    
    if topic == "wfms/lab1/state":
        print(f"State: flow={payload['flow']}, valve={payload['valve']}")
    elif topic == "wfms/lab1/ack":
        print(f"ACK: cid={payload['cid']}, ok={payload['ok']}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("127.0.0.1", 1883, keepalive=30)
client.loop_forever()
```

### Publish command example

```python
import paho.mqtt.client as mqtt
import json
import time

def send_valve_command(value):
    client = mqtt.Client()
    client.connect("127.0.0.1", 1883)
    client.loop_start()
    
    cmd = {
        "cid": f"ui_{int(time.time())}",
        "value": value,
        "by": "dashboard_user",
        "ts": int(time.time())
    }
    
    client.publish("wfms/lab1/cmd/valve", json.dumps(cmd), qos=1)
    print(f"Sent: {cmd}")
    
    time.sleep(0.5)
    client.loop_stop()
    client.disconnect()

# Bật van
send_valve_command("ON")

# Tắt van
send_valve_command("OFF")
```

---

## 📋 Checklist cho UI Developer

- [ ] Gateway fake chạy được: `python -m gateway.service --fake-uart`
- [ ] Subscribe xem được telemetry/state
- [ ] Gửi ON command → nhận ACK ok=true → state.valve="ON"
- [ ] Gửi OFF command → nhận ACK ok=true → state.valve="OFF"
- [ ] Test duplicate CID → nhận ACK ok=false, reason="duplicate_cid"
- [ ] UI hiển thị được flow, battery, valve status
- [ ] UI có button ON/OFF, generate unique CID cho mỗi lệnh
- [ ] UI handle ACK timeout (wait 3-5s, hiển thị lỗi nếu không có ACK)
- [ ] UI handle ACK errors (locked, cooldown, etc.)

---

## 🔧 Troubleshooting

### Gateway không chạy: "ModuleNotFoundError"

```bash
cd wfms
pip install -r requirements.txt
```

### MQTT connect failed: "Connection refused"

```bash
# Windows: Start Mosquitto service
Start-Service mosquitto

# Hoặc cài đặt Mosquitto
winget install EclipseFoundation.Mosquitto
```

### mosquitto_sub/pub not found

```powershell
# Add to PATH (session này)
$env:Path += ";C:\Program Files\mosquitto"

# Hoặc dùng full path
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -t "wfms/lab1/#" -v
```

### Flow không đổi khi bật/tắt van

- Đây là hành vi đúng của Fake UART
- Valve OFF: flow = 0-0.5 L/min
- Valve ON: flow = 10-25 L/min (random)

### ACK không về

- Check gateway logs: có thông báo "Published ACK" không?
- Nếu dùng `--drop-ack-prob`, đây là hành vi mong muốn (test timeout)
- Đảm bảo subscribe `wfms/lab1/ack`

---

## 📞 Hỗ trợ

Nếu có vấn đề, check:
1. Gateway logs (terminal chạy gateway)
2. CONTRACT.md (topics/payload spec)
3. README.md chính (setup môi trường)

**Lưu ý**: Gateway Fake UART chỉ để test UI. Khi deploy thật, sẽ dùng Real UART mode với Zigbee Coordinator.

---

**Happy coding! 🚀**
