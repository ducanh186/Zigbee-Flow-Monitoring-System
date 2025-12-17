# Zigbee Dashboard - UART Protocol Specification

**Version:** 1.0  
**Date:** 2025-12-17

---

## Overview

Communication protocol between Zigbee Coordinator (firmware) and PC Dashboard via UART/VCOM.

- **Baud rate:** 115200 (recommend) hoặc theo cấu hình
- **Format:** Line-based text, terminated with `\n`
- **Encoding:** ASCII/UTF-8
- **Data format:** JSON

---

## Message Types

### 1. @DATA - Telemetry từ Coordinator → PC

**Format:**
```
@DATA <json>\n
```

**JSON Schema:**
```json
{
  "v": 1,                    // Protocol version (integer)
  "ts": 1234567890,          // [Optional] Unix timestamp (seconds)
  "flow": 100,               // Flow rate (integer, L/min)
  "battery": 85,             // Battery level (integer, 0-100%)
  "valve": "open"            // Valve state: "open" or "closed"
}
```

**Examples:**
```
@DATA {"v":1,"flow":120,"battery":90,"valve":"open"}
@DATA {"v":1,"ts":1702800000,"flow":45,"battery":75,"valve":"closed"}
```

**Rules:**
- Gửi khi có thay đổi flow/battery hoặc valve state
- Có thể gửi định kỳ (e.g., mỗi 10s) để keep-alive
- `flow`: integer 0-999 (L/min)
- `battery`: integer 0-100 (%)
- `valve`: PHẢI là `"open"` hoặc `"closed"` (lowercase)

---

### 2. @CMD - Command từ PC → Coordinator

**Format:**
```
@CMD <json>\n
```

**JSON Schema:**
```json
{
  "id": 123,                 // Command ID (integer, unique per request)
  "op": "operation_name",    // Operation type (string)
  // ... operation-specific parameters
}
```

#### 2.1. Valve Control

**Operation:** `valve_set`

```json
{
  "id": 1,
  "op": "valve_set",
  "value": "open"            // "open" or "closed"
}
```

**Example:**
```
@CMD {"id":1,"op":"valve_set","value":"open"}
@CMD {"id":2,"op":"valve_set","value":"closed"}
```

#### 2.2. Threshold Configuration

**Operation:** `threshold_set`

```json
{
  "id": 3,
  "op": "threshold_set",
  "close_th": 80,            // Flow threshold to close valve (L/min)
  "open_th": 20              // Flow threshold to open valve (L/min)
}
```

**Example:**
```
@CMD {"id":3,"op":"threshold_set","close_th":80,"open_th":20}
```

**Validation rules:**
- `0 <= open_th <= close_th <= 999`
- Close threshold PHẢI >= open threshold để tránh oscillation

---

### 3. @ACK - Acknowledgment từ Coordinator → PC

**Format:**
```
@ACK <json>\n
```

**JSON Schema:**
```json
{
  "id": 123,                 // Command ID being acknowledged (integer)
  "ok": true,                // Success status (boolean)
  "msg": "description",      // [Optional] Human-readable message
  // ... echo back parameters for confirmation
}
```

#### 3.1. Valve Control ACK

```json
{
  "id": 1,
  "ok": true,
  "msg": "valve set to open",
  "valve": "open"
}
```

**Example:**
```
@ACK {"id":1,"ok":true,"msg":"valve set to open","valve":"open"}
@ACK {"id":2,"ok":false,"msg":"valve control failed"}
```

#### 3.2. Threshold Set ACK

```json
{
  "id": 3,
  "ok": true,
  "msg": "thresholds saved to NVM",
  "close_th": 80,
  "open_th": 20
}
```

**Example:**
```
@ACK {"id":3,"ok":true,"msg":"saved","close_th":80,"open_th":20}
@ACK {"id":4,"ok":false,"msg":"invalid range: open_th > close_th"}
```

---

## Error Handling

### Invalid Command
```
@ACK {"id":5,"ok":false,"msg":"unknown operation"}
```

### Parse Error
```
@ACK {"id":0,"ok":false,"msg":"json parse error"}
```

### Timeout
- PC should wait max 2 seconds for @ACK
- If no response, retry or show error in UI

---

## State Machine - Valve Control Priority

### Manual vs Auto Mode

**Suggested logic:**

1. **Auto mode (default):**
   - Valve controlled by flow thresholds
   - When `flow >= close_th` → close valve
   - When `flow <= open_th` → open valve

2. **Manual mode:**
   - Triggered by `valve_set` command
   - Overrides auto control
   - Optional: timeout after 5 minutes → back to auto
   - Optional: explicit `manual_mode` command

3. **Every valve state change:**
   - Send `@DATA` immediately to notify PC

---

## Testing Examples

### Coordinator → PC (Telemetry stream)
```
@DATA {"v":1,"flow":150,"battery":95,"valve":"open"}
@DATA {"v":1,"flow":160,"battery":95,"valve":"open"}
@DATA {"v":1,"flow":85,"battery":94,"valve":"closed"}
```

### PC → Coordinator (Commands)
```
@CMD {"id":1,"op":"valve_set","value":"open"}
@CMD {"id":2,"op":"threshold_set","close_th":100,"open_th":30}
```

### Coordinator → PC (Acknowledgments)
```
@ACK {"id":1,"ok":true,"msg":"valve opened","valve":"open"}
@ACK {"id":2,"ok":true,"msg":"saved","close_th":100,"open_th":30}
@DATA {"v":1,"flow":150,"battery":95,"valve":"open"}
```

---

## Implementation Notes

### For Firmware (Person A):
- Use line buffering for UART RX
- JSON library: cJSON (lightweight) hoặc tương tự
- Store thresholds in NVM3/token storage
- Validate all inputs before ACK

### For PC Dashboard (Person B):
- Use `pyserial` với `readline()` cho line-based parsing
- Regex match: `^@(DATA|CMD|ACK) (.+)$`
- Command ID tracking: dict để match ACK với request
- Handle COM reconnect gracefully

---

## Version History

- **v1.0 (2025-12-17):** Initial protocol specification

---

**Contact:** Sync protocol changes giữa 2 người qua Git commit hoặc chat trước khi implement!
