# WFMS Contract Specification

**VERSION**: 1.0  
**STATUS**: DO NOT BREAK  
**RULE**: Chỉ được thêm field mới. KHÔNG đổi tên, kiểu dữ liệu, hoặc xóa field cũ.

---

## MQTT Topics

Giả định `SITE = "lab1"` (configurable via .env)

### Base Topic Pattern
```
wfms/{site}/{category}
```

### Topics Specification

| Topic | QoS | Retained | Direction | Description |
|-------|-----|----------|-----------|-------------|
| `wfms/lab1/state` | 1 | Yes | Gateway → Subscribers | Trạng thái hiện tại của hệ thống |
| `wfms/lab1/telemetry` | 0 | No | Gateway → Subscribers | Dữ liệu telemetry real-time |
| `wfms/lab1/cmd/valve` | 1 | No | Dashboard → Gateway | Lệnh điều khiển van |
| `wfms/lab1/ack` | 1 | No | Gateway → Subscribers | Acknowledgment cho commands |
| `wfms/lab1/status/gateway` | 1 | Yes | Gateway → Subscribers | Gateway heartbeat/LWT |

---

## Payload Format (JSON)

### 1. Command Payload (`wfms/lab1/cmd/valve`)

```json
{
  "cid": "cmd_1673456789_abc123",
  "value": "ON",
  "by": "admin_user",
  "ts": 1673456789
}
```

**Fields:**
- `cid` (string, required): Command ID duy nhất (UUID hoặc timestamp-based)
- `value` (string, required): `"ON"` hoặc `"OFF"`
- `by` (string, required): User ID người ra lệnh
- `ts` (integer, required): Unix timestamp (seconds)

---

### 2. Acknowledgment Payload (`wfms/lab1/ack`)

```json
{
  "cid": "cmd_1673456789_abc123",
  "ok": true,
  "reason": "Valve turned ON successfully",
  "ts": 1673456790
}
```

**Fields:**
- `cid` (string, required): Command ID tương ứng
- `ok` (boolean, required): `true` nếu thành công, `false` nếu thất bại
- `reason` (string, required): Mô tả kết quả hoặc lỗi
- `ts` (integer, required): Unix timestamp khi ACK được tạo

---

### 3. State Payload (`wfms/lab1/state`, retained)

```json
{
  "flow": 12.5,
  "battery": 85,
  "valve": "ON",
  "updatedAt": 1673456790
}
```

**Fields:**
- `flow` (number, required): Lưu lượng nước (L/min)
- `battery` (number, required): Mức pin cảm biến (0-100%)
- `valve` (string, required): Trạng thái van `"ON"` hoặc `"OFF"`
- `updatedAt` (integer, required): Unix timestamp của lần cập nhật cuối

---

### 4. Telemetry Payload (`wfms/lab1/telemetry`)

```json
{
  "flow": 12.5,
  "battery": 85,
  "ts": 1673456790
}
```

**Fields:**
- `flow` (number, required): Lưu lượng nước hiện tại
- `battery` (number, required): Mức pin
- `ts` (integer, required): Unix timestamp

---

### 5. Gateway Status (`wfms/lab1/status/gateway`, retained, LWT)

```json
{
  "status": "online",
  "version": "1.0.0",
  "uptime": 3600,
  "ts": 1673456790
}
```

**Fields:**
- `status` (string, required): `"online"` hoặc `"offline"` (LWT)
- `version` (string, optional): Phiên bản gateway
- `uptime` (integer, optional): Thời gian chạy (seconds)
- `ts` (integer, required): Unix timestamp

---

## Local Admin API (localhost only)

Base URL: `http://localhost:8080`

### Endpoints

#### `GET /health`
**Response 200:**
```json
{
  "status": "ok",
  "uptime": 3600,
  "uart": "connected",
  "mqtt": "connected"
}
```

---

#### `GET /rules`
**Response 200:**
```json
{
  "lock": false,
  "cooldown_user_s": 3,
  "cooldown_global_s": 1,
  "dedupe_ttl_s": 60,
  "ack_timeout_s": 3
}
```

---

#### `POST /rules`
**Request Body:**
```json
{
  "lock": true,
  "cooldown_user_s": 5
}
```

**Response 200:**
```json
{
  "ok": true,
  "message": "Rules updated"
}
```

---

#### `GET /config`
**Response 200:**
```json
{
  "uart_port": "COM10",
  "mqtt_host": "127.0.0.1",
  "mqtt_port": 1883,
  "site": "lab1"
}
```

---

#### `POST /config`
**Request Body:**
```json
{
  "uart_port": "COM8"
}
```

**Response 200:**
```json
{
  "ok": true,
  "message": "Config updated. Restart required."
}
```

---

#### `GET /logs?tail=200`
**Query Params:**
- `tail` (integer, optional, default=100): Số dòng log gần nhất

**Response 200:**
```json
{
  "logs": [
    "[2024-01-10 10:30:00] Gateway started",
    "[2024-01-10 10:30:01] UART connected on COM10",
    "[2024-01-10 10:30:02] MQTT connected to 127.0.0.1:1883"
  ]
}
```

---

## Nguyên tắc Breaking Change

1. **Thêm field mới**: ✅ OK (phải có default value)
2. **Đổi tên field**: ❌ KHÔNG được
3. **Đổi kiểu dữ liệu**: ❌ KHÔNG được
4. **Xóa field**: ❌ KHÔNG được
5. **Thêm topic mới**: ✅ OK
6. **Đổi topic pattern**: ❌ KHÔNG được (trừ khi major version bump)

---

## Version History

- **v1.0** (2024-01-10): Initial contract
