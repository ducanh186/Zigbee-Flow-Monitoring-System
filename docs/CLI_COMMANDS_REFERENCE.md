# Zigbee CLI - Tài Liệu Tham Khảo Lệnh

> Hướng dẫn sử dụng CLI cho dự án Zigbee Flow Monitoring System

**Áp dụng:** Z3Light, Z3Switch, Sensor Node, Actuator Node, Coordinator Node, Z3Gateway

---

## Mục lục

- [Quy ước](#quy-ước)
- [1. Lệnh cơ bản](#1-lệnh-cơ-bản)
- [2. Coordinator - Quản lý mạng](#2-coordinator---quản-lý-mạng)
- [3. End Device/Router - Tham gia mạng](#3-end-devicerouter---tham-gia-mạng)
- [4. Binding](#4-binding)
- [5. ZCL Commands](#5-zcl-commands)
- [6. Debug & Diagnostics](#6-debug--diagnostics)
- [7. OTA Update](#7-ota-update)
- [8. Workflow mẫu](#8-workflow-mẫu)

---

## Quy ước

### CLI Prompt

| Prompt | Vai trò | Ứng dụng |
|--------|---------|----------|
| `Z3Light>` | Router/Light/Coordinator | Project Z3Light |
| `Z3Switch>` | Switch/Sensor/Actuator | Project Z3Switch |

### Vai trò trong mạng

- **Coordinator:** Tạo và quản lý mạng (Z3Light hoặc Z3Gateway)
- **Router:** Chuyển tiếp dữ liệu, mở rộng mạng
- **End Device:** Thiết bị đầu cuối (Sensor Node, Actuator Node)

---

## 1. Lệnh cơ bản

### Xem thông tin node

```bash
info
```

**Thông tin hiển thị:**

| Field | Ý nghĩa | Giá trị |
|-------|---------|---------|
| `chan` | Zigbee channel | 11-26 |
| `panID` | PAN ID của mạng | 0x0000-0xFFFF |
| `nodeType` | Loại node | 0x00=Coordinator, 0x02=Router, 0x03=End Device |
| `network state` | Trạng thái mạng | 0x00=No network, 0x02=Joined |

**Ví dụ:**

```text
Z3Light>info
node [...] chan [15] pwr [3]
panID [0x5140] nodeID [0x0F72]
nodeType [0x02]
network state [02]
```

### Xem danh sách lệnh

```bash
help                           # Tất cả lệnh
plugin                         # Danh sách plugins
plugin <tên-plugin>            # Chi tiết plugin cụ thể
```

**Sử dụng khi:** Quên cú pháp lệnh hoặc gặp lỗi "Incorrect number of arguments"

---

## 2. Coordinator - Quản lý mạng

### Tạo mạng

**Option 1: Cấu hình mặc định**

```bash
plugin network-creator start 0
```

- Sử dụng channel mask và cấu hình mặc định
- Nhanh chóng cho demo và testing

**Option 2: Cấu hình tùy chỉnh**

```bash
plugin network-creator form 1 0xBEEF 20 11
```

| Tham số | Ý nghĩa |
|---------|---------|
| `1` | Centralized network (Trust Center) |
| `0xBEEF` | PAN ID |
| `20` | Channel Zigbee |
| `11` | TX power (dBm) |

**Kiểm tra:** Dùng `info` để xác nhận `network state [02]`

### Mở/Đóng mạng cho join

```bash
# Mở mạng (permit join ~180s)
plugin network-creator-security open-network

# Đóng mạng
plugin network-creator-security close-network
```

**Sử dụng khi:**

- Test: cho các node khác join vào
- Bảo mật: đóng mạng sau khi join xong

### Rời mạng

```bash
network leave
```

**Sử dụng khi:**

- Muốn reset và tạo mạng mới
- Thay đổi PAN ID hoặc channel

---

## 3. End Device/Router - Tham gia mạng

### Join mạng

```bash
plugin network-steering start 0
```

**Yêu cầu:**

- Coordinator đã form mạng
- Coordinator đang open-network

**Kiểm tra:** `info` để xác nhận `chan`, `panID`, và `network state [02]`

### Rời mạng

```bash
network leave
```

---

## 4. Binding

### Xem binding table

```bash
option binding-table print
```

### Manual binding

```bash
option binding-table set <index> <clusterId> <localEp> <remoteEp> {<remoteEUI64>}
```

**Ví dụ:** Binding On/Off từ Switch → Light

```bash
option binding-table set 0 0x0006 0x01 0x01 {EUI64_Light}
option binding-table print
```

### Find & Bind (tự động)

**Trên Target (Light):**

```bash
plugin find-and-bind target 1
```

**Trên Initiator (Switch):**

```bash
plugin find-and-bind initiator 1
```

**Kiểm tra:**

```bash
option binding-table print
```

---

## 5. ZCL Commands

### On/Off commands

```bash
zcl on-off on                  # Bật
zcl on-off off                 # Tắt
zcl on-off toggle              # Đảo trạng thái
```

### Gửi command

```bash
send 0xFFFF 1 1                # Broadcast
send <nodeId> 1 1              # Unicast
```

**Sử dụng khi:** Test cluster mà không cần phần cứng (button)

---

## 6. Debug & Diagnostics

### Tắt spam log RX

```bash
option print-rx-msgs disable
```

### Xem topology mạng

```bash
plugin stack-diagnostics neighbor-table     # Các node hàng xóm
plugin stack-diagnostics child-table        # End Device con
plugin stack-diagnostics route-table        # Bảng routing
```

**Sử dụng khi:** Debug vấn đề kết nối hoặc routing

### Đọc attribute

```bash
zcl global read <clusterId> <attributeId>
send <nodeId> <srcEp> <dstEp>
```

**Ví dụ:** Đọc On/Off attribute

```bash
zcl global read 0x0006 0x0000
send 0x1234 1 1
```

---

## 7. OTA Update

### Tạo file OTA

**Bước 1: Tạo .gbl từ .s37**

```bash
commander gbl create output.gbl --app input.s37
```

**Bước 2: Tạo .ota từ .gbl**

```bash
image-builder --create output.ota \
  --version 22 \
  --manuf-id 0x1002 \
  --image-type 0 \
  --tag-id 0x0000 \
  --tag-file output.gbl \
  --string "Firmware v22"
```

### OTA Client

```bash
plugin ota-client start
```

**Yêu cầu:** OTA Server đã được cấu hình trong mạng

---

## 8. Workflow mẫu

### Demo Light & Switch

**1. Coordinator/Light:**

```bash
plugin network-creator start 0
info
```

**2. Switch:**

```bash
plugin network-steering start 0
info
```

**3. Find & Bind:**

```bash
# Trên Light
plugin find-and-bind target 1

# Trên Switch
plugin find-and-bind initiator 1
```

**4. Kiểm tra:**

```bash
option binding-table print
```

**5. Test:** Nhấn button trên Switch → LED Light bật/tắt

---

### Flow Monitoring System

**1. Coordinator:**

```bash
plugin network-creator start 0
plugin network-creator-security open-network
```

**2. Sensor Node:**

```bash
plugin network-steering start 0
info
```

**3. Actuator Node:**

```bash
plugin network-steering start 0
info
```

**4. Kiểm tra topology:**

```bash
plugin stack-diagnostics neighbor-table
plugin stack-diagnostics child-table
```

**5. Debug data flow:**

```bash
# Đọc flow value từ Sensor
zcl global read 0x000C 0x0055
send <sensorNodeId> 1 1

# Điều khiển van
zcl on-off on
send <actuatorNodeId> 1 1
```

---

## Z3Gateway (Linux/PC)

### Khởi động Gateway

```bash
sudo ./build/debug/Z3Gateway -p /dev/ttyACM0
```

**Yêu cầu:**

- Kit Zigbee chạy NCP firmware
- Kết nối USB với PC

**Chức năng:**

- Coordinator trong mạng Zigbee
- Gateway đẩy dữ liệu lên PC/Cloud

---

## Lưu ý quan trọng

⚠️ **Lỗi thường gặp:**

| Lỗi | Nguyên nhân | Giải pháp |
|-----|-------------|-----------|
| "Incorrect number of arguments" | Thiếu tham số lệnh | Dùng `plugin <tên>` xem cú pháp |
| Node không join được | Coordinator chưa open-network | `plugin network-creator-security open-network` |
| Không thấy binding | Chưa chạy Find & Bind | Chạy lại quy trình binding |
| Data không truyền | Route bị lỗi | Kiểm tra `neighbor-table` và `route-table` |

💡 **Tips:**

- Luôn dùng `info` để kiểm tra trạng thái trước khi debug
- Tắt `print-rx-msgs` để log dễ đọc hơn
- Lưu EUI64 và nodeId của các node để tiện tra cứu
- Dùng `option binding-table print` để verify binding

---

**Cập nhật:** Tài liệu này phù hợp với Gecko SDK 4.x và Simplicity Studio 5
