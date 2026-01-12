# WFMS — Water Flow Monitoring System

## Kiến trúc
- **Gateway Service**: Process nền DUY NHẤT được mở cổng nối tiếp (UART/COM).
- **Dashboards**: Kết nối qua MQTT + Local Admin API (localhost), KHÔNG trực tiếp đụng COM.

---

## 🚀 Quick Links

- **[Hướng dẫn cho UI Developer](README_FOR_UI_DEV.md)** 👈 **Bắt đầu đây nếu bạn làm Dashboard/UI**
- [CONTRACT.md](CONTRACT.md) - MQTT topics và payload format (chuẩn cứng)
- [requirements.txt](requirements.txt) - Python dependencies

---

## Yêu cầu hệ thống
- Python 3.11+
- Windows (hoặc Linux/macOS)
- MQTT Broker (Mosquitto, EMQX, hoặc tương tự)
- Zigbee Coordinator qua UART/COM

## Setup

### 1. Tạo Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 3. Cấu hình

Copy file `.env.example` thành `.env` và chỉnh sửa theo môi trường:

```bash
copy .env.example .env    # Windows
cp .env.example .env      # Linux/macOS
```

Chỉnh sửa `.env`:
- `UART_PORT`: Cổng COM (Windows: COM13, Linux: /dev/ttyUSB0)
- `MQTT_HOST`, `MQTT_PORT`: Địa chỉ MQTT broker
- `MQTT_USER`, `MQTT_PASS`: Credentials (nếu broker yêu cầu auth)

### 4. Chạy Gateway Service

**Fake UART mode (test UI mà không cần hardware):**
```bash
python -m gateway.service --fake-uart

# Hoặc double-click run_fake.ps1 (Windows)
```

**Real UART mode (với Zigbee Coordinator):**
```bash
python -m gateway.service

# Override port/baud nếu cần:
python -m gateway.service --uart COM13 --baud 115200
```

**Debug mode:**
```bash
python -m gateway.service --fake-uart --debug
```

> 💡 **Xem thêm**: [README_FOR_UI_DEV.md](README_FOR_UI_DEV.md) để biết cách test với MQTT

## Cấu trúc thư mục

```
wfms/
├── gateway/          # Gateway service (UART + MQTT + Admin API)
├── common/           # Shared constants và utilities
├── dashboards/       # Dashboard applications (Admin/User)
├── CONTRACT.md       # MQTT topics + payload + API spec
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variables template
└── README.md         # This file
```

## Ghi chú về dependencies

- **paho-mqtt==1.6.1**: Pinned version để tránh breaking changes trong v2.x
- **pyserial**: UART communication
- **fastapi + uvicorn**: Local Admin API
- **python-dotenv**: Load environment variables
- **pydantic**: Config validation

## Contract

Xem [CONTRACT.md](CONTRACT.md) để biết chi tiết về:
- MQTT topics
- Payload format (JSON)
- Local Admin API endpoints

**QUAN TRỌNG**: CONTRACT là chuẩn cứng. Chỉ được thêm field mới, KHÔNG đổi/xóa field cũ.

## Development Roadmap

- [x] Bước 1-4: Setup nền (structure, contract, config)
- [ ] Bước 5+: Gateway service implementation
- [ ] Dashboard Admin
- [ ] Dashboard User
