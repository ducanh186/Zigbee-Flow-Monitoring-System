# Zigbee Dashboard Project

Dashboard PC để monitoring và điều khiển hệ thống Zigbee flow monitoring với Coordinator firmware.

## 📋 Tổng quan

Project này bao gồm phần **PC Dashboard** (Flow 2) trong kiến trúc tổng thể:
- **Gateway Service**: Đọc dữ liệu từ UART, parse protocol, lưu database
- **Dashboard UI**: Streamlit app với cards màu, charts real-time, điều khiển valve
- **Protocol**: Giao thức chuẩn @DATA/@CMD/@ACK để tích hợp với firmware

## 🗂️ Cấu trúc project

```
zigbee_dashboard/
├── protocol.md          # Đặc tả giao thức UART (bắt buộc đọc!)
├── pc_gateway.py        # Gateway service - đọc serial, parse, lưu DB
├── dashboard.py         # Streamlit UI - cards, charts, controls
├── fake_device.py       # Fake device để test khi chưa có firmware
├── requirements.txt     # Python dependencies
├── README.md           # File này
└── telemetry.db        # SQLite database (tự động tạo)
```

## 🚀 Cài đặt

### 1. Clone và cài dependencies

```bash
cd zigbee_dashboard
pip install -r requirements.txt
```

### 2. Kiểm tra COM ports

```bash
python pc_gateway.py
```

Sẽ hiển thị danh sách ports khả dụng.

## 🎯 Chạy Dashboard

### Option 1: Với thiết bị thật (Coordinator firmware)

```bash
streamlit run dashboard.py
```

- Mở browser tự động
- Chọn COM port trong sidebar
- Click "Connect"
- Dashboard sẽ tự động cập nhật real-time

### Option 2: Test với fake device (không cần hardware)

**Terminal 1** - Chạy fake device:
```bash
python fake_device.py --mode console --interval 2
```

**Terminal 2** - Chạy dashboard với manual feed:
```bash
# Redirect fake output vào gateway
python fake_device.py --mode console | python pc_gateway.py --stdin
```

**Option 3** - Generate sample data file:
```bash
# Tạo file sample
python fake_device.py --mode sample --count 500

# Load vào database
python load_sample.py sample_data.txt
```

## 📡 Protocol Overview

Chi tiết xem file `protocol.md`. Tóm tắt:

### Coordinator → PC (Telemetry)
```
@DATA {"v":1,"flow":120,"battery":90,"valve":"open"}
```

### PC → Coordinator (Commands)
```
@CMD {"id":1,"op":"valve_set","value":"open"}
@CMD {"id":2,"op":"threshold_set","close_th":80,"open_th":20}
```

### Coordinator → PC (Acknowledgments)
```
@ACK {"id":1,"ok":true,"msg":"valve opened","valve":"open"}
```

## 🎨 Dashboard Features

### 1. Metric Cards
- **Flow Card**: Màu động theo threshold, hiển thị status (HIGH/NORMAL/LOW)
- **Battery Card**: Progress bar màu theo %, cảnh báo khi thấp
- **Valve Card**: Toggle buttons OPEN/CLOSE, badge trạng thái real-time

### 2. Charts
- **Live (5 min)**: Real-time flow + battery với threshold lines
- **Hourly**: Avg/Max/Min flow per hour, last 24h
- **Daily**: Bar chart average flow per day, last 30 days
- **Monthly**: Coming soon

### 3. Controls
- **Connection**: Select COM port, connect/disconnect
- **Threshold Settings**: Đặt close_th và open_th, apply xuống device
- **Valve Manual Control**: Override auto mode
- **Auto Refresh**: Configurable interval 1-10s

## 🔧 Development & Testing

### Test gateway độc lập

```bash
# Test với fake device
python fake_device.py --mode console | python -c "
import sys
from pc_gateway import ZigbeeGateway

gateway = ZigbeeGateway()
# Read from stdin for testing
for line in sys.stdin:
    print(f'Received: {line.strip()}')
"
```

### Test database queries

```python
from pc_gateway import ZigbeeGateway

gateway = ZigbeeGateway()

# Get recent data
rows = gateway.get_telemetry_last_n(100)
print(f"Last 100 records: {len(rows)}")

# Get hourly aggregate
hourly = gateway.get_aggregated_data('hour', limit=24)
print(f"Hourly data: {len(hourly)} hours")
```

### Inspect database

```bash
sqlite3 telemetry.db

sqlite> .schema
sqlite> SELECT COUNT(*) FROM telemetry;
sqlite> SELECT * FROM telemetry ORDER BY id DESC LIMIT 10;
```

## 🤝 Tích hợp với Firmware (Person A)

### Checklist tích hợp:

- [ ] Firmware implement protocol đúng format (xem `protocol.md`)
- [ ] Test bằng serial terminal: gửi `@CMD`, nhận `@ACK`
- [ ] Firmware gửi `@DATA` định kỳ hoặc khi có thay đổi
- [ ] Validate format JSON: `"valve":"open"` hoặc `"closed"` (lowercase!)
- [ ] Test threshold command: `threshold_set` lưu vào NVM, ACK đúng
- [ ] Test valve command: `valve_set`, ACK với echo state

### Quy trình test integration:

1. **Person A**: Flash firmware, connect USB
2. **Person B**: Chọn COM port trong dashboard, connect
3. **Verify**: Dashboard nhận `@DATA`, hiển thị metric cards
4. **Test valve**: Click OPEN/CLOSE, kiểm tra ACK và valve thật đổi trạng thái
5. **Test threshold**: Set threshold trong dashboard, verify firmware save vào NVM
6. **Auto logic**: Thay đổi flow (giả lập sensor), verify auto open/close

## 📝 Notes

### Valve Control Priority
- **Auto mode**: Flow >= close_th → close valve, flow <= open_th → open valve
- **Manual mode**: Dashboard gửi `valve_set` override auto (có thể có timeout)
- Mỗi lần valve đổi → firmware gửi `@DATA` ngay lập tức

### Database Schema
- **telemetry**: ts, flow, battery, valve, received_at
- **command_log**: cmd_id, operation, params, ack_status, ack_msg, sent_at, ack_at
- Indexes: ts, cmd_id

### Performance
- Serial read: non-blocking với timeout 1s
- Database write: mỗi `@DATA` → 1 INSERT (có thể batch sau)
- Auto refresh: 1-10s interval (configurable)

## 🐛 Troubleshooting

### Dashboard không kết nối
- Kiểm tra COM port đúng
- Verify firmware đang chạy và gửi `@DATA`
- Test bằng serial terminal (PuTTY/screen) trước

### Không nhận dữ liệu
- Check baudrate (default 115200)
- Verify protocol format (phải có `@DATA ` prefix)
- Check JSON format (dùng `json.loads()` test)

### ACK timeout
- Firmware phải trả ACK trong 2s
- Verify command format đúng (`@CMD` prefix)
- Check cmd_id matching

## 📚 References

- **Streamlit docs**: https://docs.streamlit.io/
- **Plotly charts**: https://plotly.com/python/
- **PySerial**: https://pyserial.readthedocs.io/

## 👥 Team

- **Person A (Firmware)**: Coordinator firmware, UART protocol, valve control
- **Person B (Dashboard)**: Gateway service, UI, database, charts

**Integration point**: `protocol.md` - BẮT BUỘC sync protocol changes qua Git!

---

**Version**: 1.0  
**Last update**: 2025-12-17
