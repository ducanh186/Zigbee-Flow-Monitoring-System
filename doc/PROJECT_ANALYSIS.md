# Phân Tích Đề Tài: Hệ Thống Giám Sát Lưu Lượng Nước Zigbee

## Mục lục

- [Tổng quan hệ thống](#tổng-quan-hệ-thống)
- [Yêu cầu kỹ thuật cho từng node](#yêu-cầu-kỹ-thuật-cho-từng-node)
- [Luồng dữ liệu của hệ thống](#luồng-dữ-liệu-của-hệ-thống)
- [Tính năng nâng cao](#tính-năng-nâng-cao)
- [Lộ trình triển khai khuyến nghị](#lộ-trình-triển-khai-khuyến-nghị)
- [Tóm tắt trách nhiệm chính](#tóm-tắt-trách-nhiệm-chính)

---

## Tổng quan hệ thống

Đề tài yêu cầu xây dựng một hệ thống IoT hoàn chỉnh dựa trên Zigbee với ba chức năng chính: **đo lưu lượng nước**, **điều khiển van** và **điều phối toàn bộ mạng**. Mỗi thành phần đảm nhiệm vai trò riêng nhưng phải phối hợp chặt chẽ qua các cluster chuẩn của Zigbee.

### Sensor Node – Vai trò

- **Đo lưu lượng:** đọc cảm biến dạng xung, quy đổi sang đơn vị L/min hoặc m³/h
- **Quản lý năng lượng:** vận hành bằng pin, báo cáo mức pin còn lại
- **Truyền dữ liệu:** gửi thông tin đo được cho Coordinator qua Zigbee

### Actuator Node – Vai trò

- **Điều khiển van:** nhận lệnh đóng/mở van từ Coordinator
- **Phản hồi trạng thái:** báo cáo trạng thái van hiện tại về Coordinator

### Coordinator Node – Vai trò

- **Thu thập dữ liệu:** nhận báo cáo lưu lượng và pin từ Sensor Node
- **Hiển thị thông tin:** xuất dữ liệu lên LCD hoặc UART
- **Ra quyết định:** điều khiển van tự động (theo ngưỡng) hoặc thủ công (nút nhấn, CLI, PC/mobile)

### Các hướng mở rộng

- **Z3Gateway:** tích hợp để đẩy dữ liệu lên nền tảng đám mây
- **BLE:** bổ sung giao thức BLE để tương tác với thiết bị di động
- **OTA:** cập nhật firmware từ xa cho các node

---

## Yêu cầu kỹ thuật cho từng node

### Sensor Node – Yêu cầu kỹ thuật

#### 📋 Chức năng bắt buộc

| Chức năng | Mô tả chi tiết |
|-----------|----------------|
| **Đọc cảm biến** | Sử dụng GPIO interrupt + Timer để đếm xung trong chu kỳ cố định |
| **Tính lưu lượng** | Áp dụng công thức `Flow (L/min) = pulses_per_second * K` |
| **Lưu trữ dữ liệu** | Ghi vào attribute `presentValue` của Analog Input cluster (Server) |
| **Báo cáo** | Bật reporting với ngưỡng thay đổi phù hợp |
| **Đo pin** | Đọc ADC, quy đổi sang % và lưu vào Power Configuration cluster |

#### ⚙️ Cấu hình Zigbee (ZAP)

```
Endpoint 1:
  Device Type: Simple Sensor / Custom
  
Cluster Server:
  • Basic
  • Identify
  • Power Configuration
  • Analog Input
```

#### 💻 Firmware gợi ý

- Tạo **sự kiện định kỳ** (ví dụ 1 giây) để đọc cảm biến
- Cập nhật attribute bằng `emberAfWriteAttribute()`
- Reporting plugin tự động gửi dữ liệu
- Thiết lập **End Device sleepy** mode
- Hiệu chỉnh interval và chu kỳ ngủ để cân bằng độ trễ/pin

#### ⚠️ Lưu ý vận hành

| Chế độ | Ưu điểm | Nhược điểm |
|--------|---------|------------|
| **Report nhanh** | Dữ liệu thời gian thực | Tiêu thụ pin cao |
| **Report chậm** | Tiết kiệm pin | Độ trễ cao |

### Actuator Node – Yêu cầu kỹ thuật

#### 📋 Chức năng bắt buộc

- Dùng **On/Off cluster (Server)** tương tự mẫu Z3Light
  - `On` = mở van
  - `Off` = đóng van
- Tại `emberAfPostAttributeChangeCallback()`: đọc trạng thái On/Off và điều khiển GPIO nối với driver (MOSFET/relay)

#### ⚙️ Cấu hình Zigbee (ZAP)

```
Endpoint 1:
  Device Type: On/Off Light / Custom
  
Cluster Server:
  • Basic
  • Identify
  • On/Off
  • Groups/Scenes (tùy chọn)
```

#### 🌐 Lựa chọn kiến trúc mạng

- **Nguồn ổn định → Router:** tăng độ phủ sóng mesh
- **Dùng pin → End Device:** cần đảm bảo thời gian đáp ứng van

### Coordinator Node – Yêu cầu kỹ thuật

#### 📋 Chức năng bắt buộc

**1. Nhận báo cáo lưu lượng**
   - Tạo endpoint **Analog Input Client** để tiếp nhận report `presentValue`
   - Xử lý trong callback: `emberAfAnalogInputClusterServerAttributeChangedCallback()` hoặc `emberAfClusterAttributeChangedCallback()`
   - Quy đổi sang đơn vị hiển thị phù hợp

**2. Hiển thị dữ liệu**
   - Khởi tạo **GLIB/DMD** trong `emberAfMainInitCallback()`
   - Cập nhật chuỗi hiển thị mỗi khi có dữ liệu mới
   - Ví dụ: `Flow: XX.Y L/min`

**3. Ra quyết định điều khiển**
   - Định nghĩa ngưỡng MAX/MIN
   - Gửi lệnh On/Off qua **On/Off Client**
   - Sử dụng: `emberAfFillCommandOnOffClusterOn/Off()` + `emberAfSendCommandUnicast()` hoặc binding

**4. Điều khiển thủ công**
   - Hỗ trợ nút nhấn để chuyển chế độ
   - CLI/UART commands: `flow print`, `valve on`, `valve off`

#### ⚙️ Cấu hình Zigbee (ZAP)

```
Endpoint 1:
  
  Cluster Server:
    • Basic
    • Identify
  
  Cluster Client:
    • Analog Input
    • On/Off
```

---

## Luồng dữ liệu của hệ thống

### 🌊 Luồng đo lưu lượng

```
1. Nước chảy → Cảm biến tạo xung
                    ↓
2. Sensor Node → GPIO interrupt đếm xung
                    ↓
              Timer event định kỳ tính flow
                    ↓
              Ghi vào Analog Input.presentValue
                    ↓
              Gửi ZCL Report
                    ↓
3. Coordinator → Nhận report
                    ↓
              Cập nhật currentFlow
                    ↓
              Hiển thị LCD
                    ↓
              Kiểm tra ngưỡng
                    ↓
4. Actuator ← Nhận lệnh On/Off
                    ↓
              Điều khiển GPIO van
```

### 🔋 Báo cáo tình trạng pin

**Sensor Node:**
- Đo pin mỗi 30–60 giây
- Ghi vào `Power Configuration.BatteryPercentageRemaining`
- Gửi report tự động

**Coordinator Node:**
- Hiển thị % pin trên LCD
- Ghi log qua UART để giám sát từ xa

---

## Tính năng nâng cao

### ☁️ Z3Gateway và kết nối đám mây

**Kiến trúc:**
- EFR32 làm **NCP** (Network Co-Processor)
- SBC/PC chạy **Z3GatewayHost**

**Chức năng:**
- Thu thập dữ liệu Zigbee tại host
- Đẩy lên MQTT/REST API
- Hiển thị trên dashboard đám mây

---

### 📱 Zigbee kết hợp BLE

**Multi-protocol:**
- Tận dụng khả năng dual-mode của EFR32MG12
- Chạy Zigbee + BLE song song

**BLE GATT Service:**
- Characteristic cho flow rate
- Characteristic cho trạng thái van
- App mobile đọc/ghi để xem và điều khiển

**⚠️ Cân nhắc:**
- Giới hạn RAM/Flash
- Lịch trình thời gian giữa hai giao thức
- **Khuyến nghị:** ổn định Zigbee trước, thêm BLE sau

---

### 🔄 Cập nhật OTA

**Cấu hình:**
- **Coordinator/Gateway:** bật OTA Server plugin
- **Sensor/Actuator:** bật OTA Client plugin

**Quy trình:**

1. Chuẩn bị image OTA
2. Lưu vào storage (internal/external flash, POSIX FS)
3. Client yêu cầu và tải về bản cập nhật
4. Cập nhật firmware tại chỗ

---

## Lộ trình triển khai khuyến nghị

| Bước | Mô tả | Mục tiêu |
|------|-------|----------|
| **0** | Giữ demo On/Off hiện có | Đảm bảo nền tảng hoạt động (Switch → Light) |
| **1** | Giả lập Sensor | Sensor gửi giá trị giả, Coordinator hiển thị LCD |
| **2** | Thêm Actuator | Coordinator gửi lệnh khi vượt ngưỡng, LED = van |
| **3** | Tích hợp cảm biến thật | Kết nối flow sensor, viết driver đếm xung |
| **4** | Báo cáo pin + low-power | Chuyển Sensor sang sleepy mode, tối ưu chu kỳ |
| **5** | Mở rộng (nếu còn thời gian) | Gateway/BLE/OTA |

---

## Tóm tắt trách nhiệm chính

### 🎯 Ba firmware trên EFR32MG12

| Node | Trách nhiệm chính |
|------|-------------------|
| **Sensor** | Đo lưu lượng + pin, Analog Input Server, Power Config, Reporting, low-power |
| **Actuator** | On/Off Server, điều khiển van |
| **Coordinator** | Analog Input Client + On/Off Client, LCD, logic điều khiển |

### 📝 Công việc kỹ thuật

- **Cấu hình ZAP:** định nghĩa chính xác endpoints, clusters, attributes
- **Lập trình:** xử lý callbacks trong `app.c`
- **Thiết lập luồng:** nước → sensor → Zigbee report → coordinator → quyết định → actuator
- **Mở rộng:** chuẩn bị cho Gateway/BLE/OTA khi lõi đã ổn định

---

### 💡 Kết luận

Hệ thống **Zigbee Flow Monitoring System** là một giải pháp IoT đo lường và điều khiển hoàn chỉnh, vượt xa bài thực hành bật/tắt LED cơ bản. Hệ thống có khả năng mở rộng lên các nền tảng giám sát và điều khiển hiện đại, đáp ứng yêu cầu thực tế về quản lý tài nguyên nước thông minh.

