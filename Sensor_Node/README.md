# Sensor Node — Short Summary

This firmware implements a battery-powered Zigbee sensor that periodically
sends flow and battery reports to the Coordinator.

- Behavior: joins the network, sends flow reports every ~5s (demo pattern) and
    battery reports periodically; handles rejoin with exponential backoff.
- Main source files: `app.c`, `main.c`.

Notes: flow is reported via the Flow Measurement/Analog cluster; battery via
the Power Configuration cluster. Timing values live in `app.c` (e.g. `TICK_MS`).
# Sensor Node - Node Cảm Biến Lưu Lượng

## 📋 Tổng quan

Sensor Node là thiết bị đầu cuối (End Device) trong mạng Zigbee, có nhiệm vụ đo lưu lượng nước từ cảm biến dạng xung và báo cáo dữ liệu về Coordinator. Node này vận hành bằng pin và được tối ưu hóa cho tiêu thụ năng lượng thấp.

## 🎯 Chức năng chính

### 1. Đo lưu lượng nước
- Đọc xung từ flow sensor (ví dụ: YF-S201)
- Đếm số xung trong khoảng thời gian cố định (1 giây)
- Tính toán lưu lượng theo công thức: `Flow (L/min) = pulses_per_second * K`
- K là hệ số hiệu chuẩn của cảm biến (thường ~2.25)

### 2. Đo mức pin
- Đọc điện áp pin qua ADC
- Chuyển đổi sang phần trăm pin còn lại
- Báo cáo định kỳ cho Coordinator

### 3. Báo cáo Zigbee
- Gửi dữ liệu lưu lượng qua Analog Input cluster
- Gửi mức pin qua Power Configuration cluster
- Sử dụng reporting tự động với ngưỡng thay đổi

## 🔧 Cấu hình Zigbee (ZAP)

### Device Type
- **Device Type:** Custom / Simple Sensor
- **Network Role:** End Device (Sleepy)
- **Security:** Zigbee 3.0

### Endpoint 1 Configuration

**Clusters Server:**
```
- Basic (0x0000)
- Identify (0x0003)
- Power Configuration (0x0001)
- Analog Input (Basic) (0x000C)
```

**Attributes quan trọng:**

| Cluster | Attribute | ID | Type | Mục đích |
|---------|-----------|----|----|----------|
| Analog Input | presentValue | 0x0055 | float | Giá trị lưu lượng hiện tại |
| Power Config | BatteryPercentageRemaining | 0x0021 | uint8 | % pin còn lại |

### Reporting Configuration

**Analog Input - presentValue:**
- Min Interval: 5 seconds
- Max Interval: 60 seconds
- Reportable Change: 0.5 L/min

**Power Configuration - Battery:**
- Min Interval: 30 seconds
- Max Interval: 300 seconds (5 phút)
- Reportable Change: 5%

## 📊 Luồng hoạt động

```
┌─────────────────────────────────────────────────┐
│  SENSOR NODE OPERATION FLOW                     │
└─────────────────────────────────────────────────┘

[Power On / Wake Up]
        │
        ↓
[Initialize Hardware]
├─ GPIO interrupt setup
├─ ADC initialization
└─ Zigbee stack init
        │
        ↓
[Join Network] ──(nếu chưa join)──> [Association Process]
        │
        ↓
[Main Loop - Event Driven]
        │
        ├──> [Flow Reading Event - 1s periodic]
        │    ├─ Đếm xung từ interrupt
        │    ├─ Tính flow rate
        │    ├─ Cập nhật presentValue attribute
        │    └─ Reporting tự động gửi nếu có thay đổi
        │
        ├──> [Battery Reading Event - 30s periodic]
        │    ├─ Đọc ADC
        │    ├─ Tính % pin
        │    ├─ Cập nhật Battery attribute
        │    └─ Reporting tự động gửi
        │
        └──> [Sleep] ──> [Wake on timer/interrupt]
                              │
                              └────> [Main Loop]
```


### Các hàm callback quan trọng

```c
// 1. Khởi tạo
void emberAfMainInitCallback(void) {
    // Init GPIO interrupt cho flow sensor
    // Init ADC cho battery
    // Setup periodic events
}

// 2. Event handler
void emberAfMainTickCallback(void) {
    // Xử lý flow reading event
    // Xử lý battery reading event
}

// 3. Stack status
void emberAfStackStatusCallback(EmberStatus status) {
    // Xử lý khi join network thành công
}
```

### Pseudocode chính

```c
// Flow sensor interrupt handler
void flowSensorISR(void) {
    pulse_count++;
}

// Flow reading event (1 second periodic)
void readFlowSensor(void) {
    float flow = pulse_count * CALIBRATION_FACTOR;
    pulse_count = 0;
    
    // Write to Zigbee attribute
    emberAfWriteServerAttribute(
        ENDPOINT,
        ZCL_ANALOG_INPUT_CLUSTER_ID,
        ZCL_PRESENT_VALUE_ATTRIBUTE_ID,
        (uint8_t*)&flow,
        ZCL_SINGLE_PRECISION_ATTRIBUTE_TYPE
    );
}

// Battery reading event (30 second periodic)
void readBattery(void) {
    uint16_t adc_value = readADC(BATTERY_ADC_CHANNEL);
    uint8_t percentage = calculateBatteryPercentage(adc_value);
    
    // Write to Zigbee attribute
    emberAfWriteServerAttribute(
        ENDPOINT,
        ZCL_POWER_CONFIG_CLUSTER_ID,
        ZCL_BATTERY_PERCENTAGE_REMAINING_ATTRIBUTE_ID,
        &percentage,
        ZCL_INT8U_ATTRIBUTE_TYPE
    );
}
```

## ⚙️ Cấu hình Plugin

### Plugins cần bật trong ZAP:

- ✅ **Reporting** - Tự động gửi report khi attribute thay đổi
- ✅ **Idle/Sleep** - Quản lý sleep mode
- ✅ **End Device Support** - Hỗ trợ End Device
- ✅ **Network Steering** - Tự động join network
- ✅ **Update TC Link Key** - Bảo mật Zigbee 3.0

### Power Management

```c
// Enable sleep
emberAfPluginIdleSleepOkToSleepCallback() {
    return true; // Cho phép sleep khi không có việc
}

// Sleep duration
#define SLEEP_DURATION_MS 1000 // Wake up mỗi 1 giây
```

## 🔋 Tối ưu năng lượng

### Các biện pháp tiết kiệm pin:

1. **Sleep Mode:**
   - Sử dụng EM2 sleep mode
   - Wake up bằng timer hoặc interrupt

2. **Reporting Interval:**
   - Max interval 60s cho flow
   - Max interval 300s cho battery
   - Chỉ gửi khi có thay đổi đáng kể

3. **Zigbee Configuration:**
   - Poll rate thấp (7.68s)
   - Short poll khi cần nhận data nhanh

### Ước tính thời lượng pin

| Chế độ | Dòng tiêu thụ | Thời gian |
|--------|---------------|-----------|
| Active (TX/RX) | ~20mA | 1% thời gian |
| Idle/Sleep (EM2) | ~2μA | 99% thời gian |
| **Trung bình** | **~0.2mA** | - |
| **Pin 2000mAh** | - | **~1 năm** |

## 🧪 Testing và Debug

### Test Cases

1. **Flow Sensor:**
   - Không có nước chảy → flow = 0
   - Nước chảy ổn định → flow ổn định
   - Thay đổi lưu lượng → giá trị cập nhật

2. **Battery Reporting:**
   - Pin đầy → 100%
   - Pin yếu → cảnh báo

3. **Zigbee Network:**
   - Join thành công
   - Report tự động gửi
   - Coordinator nhận được data

### CLI Commands (Debug)

```bash
# Kiểm tra network
plugin network-steering status

# Đọc attribute local
zcl global read 0x000C 0x0055  # Analog Input

# Force send report
plugin reporting print

# Check sleep status
plugin idle-sleep status
```

