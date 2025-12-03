# Actuator Node - Node Điều Khiển Van

## 📋 Tổng quan

Actuator Node là thiết bị điều khiển van nước trong hệ thống, nhận lệnh từ Coordinator qua mạng Zigbee và thực hiện đóng/mở van. Node này có thể hoạt động như Router (nếu cấp nguồn ổn định) hoặc End Device (nếu dùng pin).

## 🎯 Chức năng chính

### 1. Nhận lệnh điều khiển
- Nhận On/Off command từ Coordinator
- Xử lý command trong callback
- Cập nhật trạng thái attribute

### 2. Điều khiển van
- Mở van khi nhận lệnh ON
- Đóng van khi nhận lệnh OFF
- Điều khiển GPIO để kích hoạt relay/MOSFET

### 3. Phản hồi trạng thái
- Báo cáo trạng thái van hiện tại
- Đồng bộ attribute với trạng thái thật

## 🔌 Kết nối phần cứng

```
EFR32MG12 Development Kit
    │
    ├─── GPIO Output ──────> MOSFET Gate / Relay Control
    │                         │
    │                         ↓
    │                    [Driver Circuit]
    │                         │
    │                         ↓
    │                    Solenoid Valve
    │                    (12V / 24V DC)
    │
    └─── LED (debug) ─────> Status Indicator
```

### Pin mapping gợi ý

| Chức năng | Pin | Mô tả |
|-----------|-----|-------|
| Valve Control | PF5 | GPIO output điều khiển relay/MOSFET |
| Status LED | PF6 | LED hiển thị trạng thái van |
| Button (tùy chọn) | PF7 | Nút nhấn local control |

### Sơ đồ driver đơn giản

```
GPIO (3.3V) ──> [1kΩ] ──> MOSFET Gate (IRLZ44N)
                              │
                         Drain │
                              ↓
                    Valve Coil (+)
                              │
                              GND
                              
Valve Coil (-) ──> VCC (12V)
```

## 🔧 Cấu hình Zigbee (ZAP)

### Device Type
- **Device Type:** On/Off Light (hoặc Custom)
- **Network Role:** Router (khuyến nghị) hoặc End Device
- **Security:** Zigbee 3.0

### Endpoint 1 Configuration

**Clusters Server:**
```
- Basic (0x0000)
- Identify (0x0003)
- Groups (0x0004) - tùy chọn
- Scenes (0x0005) - tùy chọn
- On/Off (0x0006)
```

**Attributes quan trọng:**

| Cluster | Attribute | ID | Type | Mục đích |
|---------|-----------|----|----|----------|
| On/Off | OnOff | 0x0000 | boolean | Trạng thái van: 0=đóng, 1=mở |

### Command Handlers

Node phải xử lý các command sau:

| Command | ID | Mô tả |
|---------|----|----|
| Off | 0x00 | Đóng van |
| On | 0x01 | Mở van |
| Toggle | 0x02 | Đảo trạng thái (tùy chọn) |

## 📊 Luồng hoạt động

```
┌─────────────────────────────────────────────────┐
│  ACTUATOR NODE OPERATION FLOW                   │
└─────────────────────────────────────────────────┘

[Power On]
    │
    ↓
[Initialize Hardware]
├─ GPIO output setup (Valve control)
├─ LED setup
└─ Zigbee stack init
    │
    ↓
[Join Network / Form Network]
├─ Router: Có thể route traffic
└─ End Device: Chỉ giao tiếp với parent
    │
    ↓
[Main Loop - Command Driven]
    │
    ├──> [Nhận On/Off Command]
    │    │
    │    ├─ Command = ON
    │    │  ├─ Set OnOff attribute = 1
    │    │  ├─ GPIO HIGH → Mở van
    │    │  └─ LED ON
    │    │
    │    └─ Command = OFF
    │       ├─ Set OnOff attribute = 0
    │       ├─ GPIO LOW → Đóng van
    │       └─ LED OFF
    │
    └──> [Local Button Press] (tùy chọn)
         └─ Toggle valve manually
              │
              └─> Update attribute & report
```

## 💻 Cấu trúc code chính

### File quan trọng

```
src/
├── app.c                      # Main application logic
├── valve_control.c/.h         # Valve driver
└── [tên_project]_callbacks.c # Zigbee callbacks
```

### Các hàm callback quan trọng

```c
// 1. Khởi tạo
void emberAfMainInitCallback(void) {
    // Init GPIO cho valve control
    // Init LED
    // Setup button (nếu có)
}

// 2. Xử lý attribute change
void emberAfPostAttributeChangeCallback(
    uint8_t endpoint,
    EmberAfClusterId clusterId,
    EmberAfAttributeId attributeId,
    uint8_t mask,
    uint16_t manufacturerCode,
    uint8_t type,
    uint8_t size,
    uint8_t* value
) {
    // Khi OnOff attribute thay đổi
    if (clusterId == ZCL_ON_OFF_CLUSTER_ID && 
        attributeId == ZCL_ON_OFF_ATTRIBUTE_ID) {
        
        bool onOff = *value;
        controlValve(onOff);
    }
}

// 3. Stack status
void emberAfStackStatusCallback(EmberStatus status) {
    if (status == EMBER_NETWORK_UP) {
        // Network joined successfully
    }
}
```

### Pseudocode điều khiển van

```c
// Valve control driver
void controlValve(bool state) {
    if (state) {
        // Mở van
        GPIO_PinOutSet(VALVE_GPIO_PORT, VALVE_GPIO_PIN);
        GPIO_PinOutSet(LED_PORT, LED_PIN);
        emberAfAppPrintln("Valve OPEN");
    } else {
        // Đóng van
        GPIO_PinOutClear(VALVE_GPIO_PORT, VALVE_GPIO_PIN);
        GPIO_PinOutClear(LED_PORT, LED_PIN);
        emberAfAppPrintln("Valve CLOSED");
    }
}

// Đọc trạng thái hiện tại
bool getValveState(void) {
    uint8_t state;
    emberAfReadServerAttribute(
        ENDPOINT,
        ZCL_ON_OFF_CLUSTER_ID,
        ZCL_ON_OFF_ATTRIBUTE_ID,
        &state,
        sizeof(state)
    );
    return (bool)state;
}

// Local button handler (tùy chọn)
void buttonCallback(uint8_t button, uint8_t state) {
    if (state == BUTTON_PRESSED) {
        // Toggle valve
        bool currentState = getValveState();
        controlValve(!currentState);
        
        // Update attribute để sync với Coordinator
        uint8_t newState = !currentState;
        emberAfWriteServerAttribute(
            ENDPOINT,
            ZCL_ON_OFF_CLUSTER_ID,
            ZCL_ON_OFF_ATTRIBUTE_ID,
            &newState,
            ZCL_BOOLEAN_ATTRIBUTE_TYPE
        );
    }
}
```

## ⚙️ Cấu hình Plugin

### Plugins cần bật trong ZAP:

- ✅ **On/Off Server Cluster** - Xử lý On/Off commands
- ✅ **Network Steering** - Join network tự động
- ✅ **Update TC Link Key** - Bảo mật Zigbee 3.0
- ⚠️ **Idle/Sleep** - Chỉ bật nếu dùng End Device với pin

### Router vs End Device

**Router Mode (Khuyến nghị):**
- Cấp nguồn liên tục (12V/24V adapter)
- Giúp mở rộng mạng mesh
- Luôn sẵn sàng nhận lệnh
- Có thể relay traffic cho node khác

**End Device Mode:**
- Chỉ dùng nếu bắt buộc dùng pin
- Thời gian đáp ứng chậm hơn
- Cần cân nhắc về độ tin cậy

## 🔄 Binding và Group

### Option 1: Unicast (Direct)
Coordinator gửi lệnh trực tiếp đến nodeId của Actuator.

```c
// Coordinator code
emberAfFillCommandOnOffClusterOn();
emberAfSendCommandUnicast(EMBER_OUTGOING_DIRECT, actuatorNodeId);
```

### Option 2: Binding
Tạo binding table để Coordinator không cần biết nodeId.

```bash
# CLI để tạo binding
zdo bind <dst-addr> <src-ep> <dst-ep> <cluster> <dst-eui64> <dst-ep>
```

### Option 3: Group
Thêm Actuator vào group, Coordinator gửi lệnh multicast.

```c
// Thêm vào group 0x0001
emberAfGroupsClusterAddGroupCallback(1, "Valves");
```

## 🔒 Bảo vệ và an toàn

### Các tính năng bảo vệ nên có:

1. **Watchdog timer:**
   - Reset nếu firmware bị treo
   - Đưa van về trạng thái an toàn

2. **Power failure handling:**
   - Lưu trạng thái vào NVM
   - Khôi phục trạng thái sau khi mất điện

3. **Manual override:**
   - Nút nhấn local để điều khiển khẩn cấp
   - Không phụ thuộc vào mạng Zigbee

4. **Safety timeout:**
   - Tự động đóng van sau thời gian nhất định
   - Tránh van mở quá lâu gây lãng phí

```c
// Ví dụ safety timeout
#define VALVE_TIMEOUT_MS (60 * 60 * 1000) // 1 giờ

void valveTimeoutHandler(void) {
    if (getValveState() == true) {
        emberAfAppPrintln("Safety timeout - closing valve");
        controlValve(false);
    }
}
```

## 🧪 Testing và Debug

### Test Cases

1. **Remote Control:**
   - Coordinator gửi ON → Van mở
   - Coordinator gửi OFF → Van đóng
   - Kiểm tra phản hồi attribute

2. **Local Control:**
   - Nhấn nút → Van toggle
   - Attribute đồng bộ với Coordinator

3. **Network Recovery:**
   - Mất kết nối → van giữ trạng thái cuối
   - Reconnect → trạng thái sync lại

4. **Power Cycle:**
   - Tắt nguồn → bật lại
   - Van khôi phục trạng thái từ NVM

### CLI Commands (Debug)

```bash
# Kiểm tra attribute
zcl global read 0x0006 0x0000  # On/Off cluster

# Gửi command local
zcl on-off on
zcl on-off off

# Kiểm tra binding table
option binding-table print

# Network status
info
```

## 🚀 Bắt đầu nhanh

1. **Import Z3Light example** vào Simplicity Studio
2. **Modify callbacks** để điều khiển GPIO thay vì LED
3. **Cấu hình ZAP** nếu cần thay đổi
4. **Thêm valve driver** code
5. **Build và flash** vào kit
6. **Test** với Coordinator

## 📚 Tài liệu tham khảo

- [Zigbee Cluster Library - On/Off Cluster](https://zigbeealliance.org/wp-content/uploads/2019/12/07-5123-06-zigbee-cluster-library-specification.pdf)
- [Z3Light Example Documentation](https://www.silabs.com/documents/public/example-code/an1199-zigbee-lighting-applications.pdf)
- [Zigbee Binding and Groups](https://www.silabs.com/documents/public/user-guides/ug391-zigbee-app-framework-dev-guide.pdf)

## ⚡ Tips phát triển

**💡 Tip 1:** Bắt đầu với Z3Light example có sẵn, chỉ cần thay hàm `led_turn_on/off()` bằng `controlValve()`.

**💡 Tip 2:** Dùng LED để debug trước khi nối van thật.

**💡 Tip 3:** Nếu dùng relay module, có thể cần thêm optocoupler để cách ly.

**💡 Tip 4:** Test với load nhỏ (LED, bóng đèn) trước khi nối van công suất lớn.

## ❓ FAQ

**Q: Van không hoạt động khi nhận lệnh?**
A: Kiểm tra GPIO output level, driver circuit (relay/MOSFET), và nguồn cấp cho van.

**Q: Làm sao để van hoạt động ngay cả khi mất kết nối Zigbee?**
A: Thêm local control bằng nút nhấn, hoặc timer tự động đóng/mở.

**Q: Node Router có tốn nhiều điện không?**
A: Có, Router luôn bật RF (~30-50mA). Nếu muốn tiết kiệm, dùng End Device nhưng sẽ chậm hơn.

**Q: Có thể điều khiển nhiều van cùng lúc?**
A: Có, dùng Group addressing hoặc broadcast command.

---

**Cập nhật:** Tài liệu này sẽ được bổ sung khi có source code cụ thể.
