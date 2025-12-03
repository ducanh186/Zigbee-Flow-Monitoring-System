# Hệ Thống Giám Sát Lưu Lượng Nước Zigbee

## 📋 Tổng quan

Hệ thống giám sát và điều khiển lưu lượng nước thông minh sử dụng mạng Zigbee, bao gồm ba node chính:
- **Sensor Node:** đo lưu lượng nước và mức pin
- **Actuator Node:** điều khiển van nước
- **Coordinator Node:** điều phối mạng, hiển thị dữ liệu và ra quyết định

## 🏗️ Cấu trúc thư mục

```
Zigbee-Flow-Monitoring-System/
│
├── Sensor Node/              # Node cảm biến lưu lượng
│   ├── README.md            # Tài liệu Sensor Node
│   └── src/                 # Source code (sẽ được thêm)
│
├── Actuator Node/           # Node điều khiển van
│   ├── README.md            # Tài liệu Actuator Node
│   └── src/                 # Source code (sẽ được thêm)
│
├── Coordinator Node/        # Node điều phối trung tâm
│   ├── README.md            # Tài liệu Coordinator Node
│   └── src/                 # Source code (sẽ được thêm)
│
├── doc/                     # Tài liệu chung
│   └── ...
│
├── PROJECT_ANALYSIS.md      # Phân tích chi tiết đề tài
└── README.md               # File này
```

## 🚀 Bắt đầu nhanh

### Yêu cầu hệ thống

- **Hardware:** 3x EFR32MG12 Development Kit
- **Software:** 
  - Simplicity Studio 5
  - Gecko SDK 4.x
  - Zigbee SDK
- **Cảm biến:** Flow sensor dạng xung (ví dụ: YF-S201)
- **Actuator:** Van điện tử hoặc solenoid valve

### Các bước triển khai

1. **Chuẩn bị phần cứng:**
   - Kết nối flow sensor với Sensor Node
   - Kết nối van điều khiển với Actuator Node
   - Kết nối LCD với Coordinator Node (tùy chọn)

2. **Cấu hình firmware:**
   - Đọc tài liệu trong từng thư mục node
   - Cấu hình ZAP file cho mỗi node
   - Build và flash firmware

3. **Tạo mạng Zigbee:**
   - Khởi động Coordinator để tạo network
   - Join Sensor Node và Actuator Node vào mạng
   - Kiểm tra kết nối

4. **Kiểm thử:**
   - Kiểm tra đo lưu lượng từ Sensor
   - Kiểm tra điều khiển van từ Coordinator
   - Kiểm tra hiển thị trên LCD/UART

## 📚 Tài liệu chi tiết

- **[PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md)** - Phân tích chi tiết yêu cầu kỹ thuật và kiến trúc hệ thống
- **[Sensor Node/README.md](Sensor%20Node/README.md)** - Hướng dẫn cấu hình và lập trình Sensor Node
- **[Actuator Node/README.md](Actuator%20Node/README.md)** - Hướng dẫn cấu hình và lập trình Actuator Node
- **[Coordinator Node/README.md](Coordinator%20Node/README.md)** - Hướng dẫn cấu hình và lập trình Coordinator Node

## 🔄 Luồng hoạt động cơ bản

```
┌─────────────┐      Zigbee Report      ┌─────────────┐
│   Sensor    │ ──────────────────────> │ Coordinator │
│    Node     │   (Flow + Battery)      │    Node     │
└─────────────┘                         └─────────────┘
      ↑                                        │
      │                                        │ On/Off Command
      │                                        ↓
  Flow Sensor                           ┌─────────────┐
   (Pulse)                              │  Actuator   │
                                        │    Node     │
                                        └─────────────┘
                                               │
                                               ↓
                                          Valve Control
```

## 🛠️ Phát triển

### Roadmap

- [x] Phân tích yêu cầu và thiết kế kiến trúc
- [ ] Sensor Node: đọc flow sensor giả lập
- [ ] Coordinator Node: nhận data và hiển thị LCD
- [ ] Actuator Node: điều khiển LED (mô phỏng van)
- [ ] Tích hợp cảm biến thật
- [ ] Báo cáo pin và low-power mode
- [ ] OTA update (nâng cao)
- [ ] Z3Gateway + Cloud (nâng cao)
- [ ] BLE integration (nâng cao)

### Đóng góp

1. Fork repository
2. Tạo branch cho tính năng mới (`git checkout -b feature/AmazingFeature`)
3. Commit thay đổi (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Tạo Pull Request

## 📄 License

Dự án này được phát triển cho mục đích học tập và nghiên cứu.

## 👥 Tác giả

- **Đức Anh** - [ducanh186](https://github.com/ducanh186)

## 🙏 Tham khảo

- Silicon Labs Zigbee Documentation
- Zigbee Cluster Library Specification
- EFR32MG12 Reference Manual
