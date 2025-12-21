# Coordinator Node — Short Summary

This firmware implements the Zigbee Coordinator and a UART JSON gateway.

- Behavior: manages the Zigbee network, receives flow and battery reports,
    performs simple auto-control (close valve when flow > threshold; open when
    flow == 0), and emits UART messages prefixed with `@DATA`, `@LOG`,
    `@INFO`, and `@ACK`.
- Control: accepts `@CMD` JSON over UART for operations such as
    `valve_set`, `threshold_set`, `net_cfg_set`, and `net_form`.

Main sources: `app.c`, `main.c`.

Refer to source files for implementation details.
# Coordinator Node - Node Điều Phối Trung Tâm

## 📋 Tổng quan

Coordinator Node là trung tâm điều phối của mạng Zigbee, có nhiệm vụ:
- Tạo và quản lý mạng Zigbee
- Thu thập dữ liệu từ Sensor Node
- Hiển thị thông tin lên LCD và UART
- Ra quyết định điều khiển Actuator Node (tự động hoặc thủ công)

## 🎯 Chức năng chính

### 1. Quản lý mạng
- Tạo mạng Zigbee mới (PAN ID, channel, security)
- Permit join để các node khác tham gia
- Quản lý routing table
- Trust Center cho bảo mật

### 2. Thu thập dữ liệu
- Nhận report lưu lượng từ Sensor Node (Analog Input cluster)
- Nhận báo cáo pin từ Sensor Node
- Lưu trữ dữ liệu trong buffer
- Xử lý dữ liệu (filter, average, ...)

### 3. Hiển thị thông tin
- LCD: Hiển thị lưu lượng, pin, trạng thái van
- UART: Gửi dữ liệu cho PC dashboard
- CLI: Nhận lệnh từ người dùng

### 4. Logic điều khiển
- **Tự động:** Đóng/mở van dựa trên ngưỡng lưu lượng
- **Thủ công:** Nhận lệnh từ nút nhấn, CLI, hoặc PC
- Gửi On/Off command tới Actuator Node



## 🔧 Cấu hình Zigbee (ZAP)

### Device Type
- **Device Type:** Custom / Gateway
- **Network Role:** Coordinator
- **Security:** Zigbee 3.0 (Trust Center)

### Endpoint 1 Configuration

**Clusters Server:**
```
- Basic (0x0000)
- Identify (0x0003)
```

**Clusters Client:**
```
- Analog Input (0x000C)    # Nhận flow data từ Sensor
- Power Config (0x0001)    # Nhận battery data
- On/Off (0x0006)          # Gửi lệnh tới Actuator
```

### Attributes quan trọng

Coordinator là **Client**, nên không có attribute riêng. Nhưng cần xử lý:

| Cluster | Direction | Mục đích |
|---------|-----------|----------|
| Analog Input | Server → Client | Nhận report flow từ Sensor |
| Power Config | Server → Client | Nhận report battery |
| On/Off | Client → Server | Gửi lệnh tới Actuator |

## 📊 Luồng hoạt động

```
┌──────────────────────────────────────────────────────┐
│  COORDINATOR NODE OPERATION FLOW                     │
└──────────────────────────────────────────────────────┘

[Power On]
    │
    ↓
[Initialize Hardware]
├─ LCD initialization (GLIB/DMD)
├─ UART setup (115200 baud)
├─ GPIO button interrupts
└─ Zigbee stack init
    │
    ↓
[Form Network]
├─ Create PAN
├─ Select channel
├─ Setup security (Trust Center)
└─ Permit join (60s default)
    │
    ↓
[Main Loop - Event Driven]
    │
    ├──> [Nhận Flow Report từ Sensor]
    │    │
    │    ├─ Parse Analog Input report
    │    ├─ Lưu vào currentFlow variable
    │    ├─ Update LCD: "Flow: XX.Y L/min"
    │    │
    │    └─> [Auto Control Logic]
    │         ├─ if (flow > MAX_THRESHOLD)
    │         │   └─> Send OFF command → Actuator
    │         │
    │         └─ if (flow < MIN_THRESHOLD)
    │             └─> Send ON command → Actuator
    │
    ├──> [Nhận Battery Report từ Sensor]
    │    ├─ Parse Power Config report
    │    ├─ Lưu vào batteryLevel variable
    │    └─ Update LCD: "Battery: XX%"
    │
    ├──> [Button Press Event]
    │    ├─ BTN0: Toggle Auto/Manual mode
    │    │   └─> Update mode, LED indicator
    │    │
    │    └─ BTN1: Manual valve control
    │        └─> Send ON/OFF toggle → Actuator
    │
    ├──> [UART Command từ PC]
    │    ├─ "flow" → Print current flow
    │    ├─ "valve on" → Open valve
    │    ├─ "valve off" → Close valve
    │    └─ "mode auto/manual" → Change mode
    │
    └──> [LCD Update Timer]
         └─> Refresh display (1 Hz)
```


### Các hàm callback quan trọng

```c
// 1. Khởi tạo
void emberAfMainInitCallback(void) {
    // Init LCD (GLIB_contextInit)
    // Init UART
    // Setup buttons
    // Init variables
    initDisplay();
    initUART();
    setupButtons();
}

// 2. Main tick (định kỳ)
void emberAfMainTickCallback(void) {
    // Update LCD display
    // Check UART input
    // Polling tasks
}

// 3. Network status
void emberAfStackStatusCallback(EmberStatus status) {
    if (status == EMBER_NETWORK_UP) {
        emberAfAppPrintln("Network formed successfully");
        displayNetworkStatus(true);
    }
}

// 4. Nhận report từ Sensor
void emberAfReportAttributesCallback(
    EmberAfClusterId clusterId,
    uint8_t *buffer,
    uint16_t bufLen
) {
    if (clusterId == ZCL_ANALOG_INPUT_CLUSTER_ID) {
        // Parse flow data
        float flowRate = parseFloatFromReport(buffer);
        updateFlowDisplay(flowRate);
        checkAutoControl(flowRate);
    }
    
    if (clusterId == ZCL_POWER_CONFIG_CLUSTER_ID) {
        // Parse battery data
        uint8_t batteryPercent = buffer[0];
        updateBatteryDisplay(batteryPercent);
    }
}
```

### Pseudocode chính

```c
// Global variables
float currentFlow = 0.0;
uint8_t batteryLevel = 100;
bool autoMode = true;
bool valveState = false;

// Threshold configuration
#define MAX_FLOW_THRESHOLD 10.0  // L/min
#define MIN_FLOW_THRESHOLD 0.5   // L/min

// Auto control logic
void checkAutoControl(float flow) {
    if (!autoMode) return;  // Skip if manual mode
    
    if (flow > MAX_FLOW_THRESHOLD) {
        if (valveState == true) {
            emberAfAppPrintln("Flow too high - closing valve");
            sendValveCommand(false);  // Close valve
        }
    }
    
    if (flow < MIN_FLOW_THRESHOLD) {
        if (valveState == false) {
            emberAfAppPrintln("Flow too low - opening valve");
            sendValveCommand(true);   // Open valve
        }
    }
}

// Gửi lệnh tới Actuator
void sendValveCommand(bool state) {
    EmberAfStatus status;
    
    if (state) {
        emberAfFillCommandOnOffClusterOn();
    } else {
        emberAfFillCommandOnOffClusterOff();
    }
    
    // Option 1: Unicast
    status = emberAfSendCommandUnicast(
        EMBER_OUTGOING_DIRECT,
        actuatorNodeId
    );
    
    // Option 2: Binding
    // status = emberAfSendCommandUnicastToBindings();
    
    if (status == EMBER_SUCCESS) {
        valveState = state;
        updateValveDisplay(state);
    }
}

// LCD display update
void updateDisplay(void) {
    GLIB_Context_t glibContext;
    char buffer[32];
    
    GLIB_clear(&glibContext);
    
    // Title
    GLIB_drawString(&glibContext, "Flow Monitor", 0, 0);
    
    // Flow value
    snprintf(buffer, 32, "Flow: %.1f L/min", currentFlow);
    GLIB_drawString(&glibContext, buffer, 0, 20);
    
    // Battery
    snprintf(buffer, 32, "Battery: %d%%", batteryLevel);
    GLIB_drawString(&glibContext, buffer, 0, 40);
    
    // Valve status
    snprintf(buffer, 32, "Valve: %s", valveState ? "OPEN" : "CLOSED");
    GLIB_drawString(&glibContext, buffer, 0, 60);
    
    // Mode
    snprintf(buffer, 32, "Mode: %s", autoMode ? "AUTO" : "MANUAL");
    GLIB_drawString(&glibContext, buffer, 0, 80);
    
    DMD_updateDisplay();
}

// Button callback
void buttonCallback(uint8_t button, uint8_t state) {
    if (state != BUTTON_PRESSED) return;
    
    if (button == BUTTON0) {
        // Toggle mode
        autoMode = !autoMode;
        emberAfAppPrintln("Mode: %s", autoMode ? "AUTO" : "MANUAL");
        updateDisplay();
    }
    
    if (button == BUTTON1) {
        // Manual valve control
        if (!autoMode) {
            sendValveCommand(!valveState);
        }
    }
}

// UART command handler
void processUARTCommand(char* cmd) {
    if (strcmp(cmd, "flow") == 0) {
        emberAfAppPrintln("Current flow: %.1f L/min", currentFlow);
    }
    else if (strcmp(cmd, "valve on") == 0) {
        sendValveCommand(true);
    }
    else if (strcmp(cmd, "valve off") == 0) {
        sendValveCommand(false);
    }
    else if (strcmp(cmd, "mode auto") == 0) {
        autoMode = true;
        emberAfAppPrintln("Auto mode enabled");
    }
    else if (strcmp(cmd, "mode manual") == 0) {
        autoMode = false;
        emberAfAppPrintln("Manual mode enabled");
    }
    else if (strcmp(cmd, "status") == 0) {
        printSystemStatus();
    }
}
```

## ⚙️ Cấu hình Plugin

### Plugins cần bật trong ZAP:

- ✅ **Network Creator** - Tạo mạng Zigbee
- ✅ **Network Creator Security** - Trust Center
- ✅ **Reporting** - Nhận report từ Sensor
- ✅ **On/Off Client** - Gửi lệnh tới Actuator
- ✅ **Command Relay** - Forward commands
- ✅ **Concentrator** - Tối ưu routing (khuyến nghị)

### Network Configuration

```c
// Network parameters
#define NETWORK_CHANNEL 15
#define NETWORK_PAN_ID 0x1A62
#define PERMIT_JOIN_DURATION 180  // 3 phút

// Form network
EmberStatus status = emberAfPluginNetworkCreatorStart(true);
```

## 🖥️ LCD Display

### GLIB Setup

```c
#include "glib.h"
#include "dmd.h"

GLIB_Context_t glibContext;

void initDisplay(void) {
    DMD_init(0);
    GLIB_contextInit(&glibContext);
    glibContext.backgroundColor = White;
    glibContext.foregroundColor = Black;
    
    GLIB_clear(&glibContext);
    GLIB_drawString(&glibContext, "Initializing...", 0, 0);
    DMD_updateDisplay();
}
```

### Layout suggestion

```
┌────────────────────────┐
│   Flow Monitor v1.0    │ <- Title
├────────────────────────┤
│                        │
│  Flow: 5.2 L/min      │ <- Current flow
│  Battery: 87%         │ <- Sensor battery
│                        │
│  Valve: OPEN          │ <- Valve status
│  Mode: AUTO           │ <- Control mode
│                        │
│  Sensor: OK           │ <- Sensor status
│  Network: 3 nodes     │ <- Network info
│                        │
└────────────────────────┘
```

## 📡 UART Interface

### Command List

| Command | Description | Example |
|---------|-------------|---------|
| `flow` | Hiển thị lưu lượng hiện tại | `> flow` |
| `battery` | Hiển thị mức pin sensor | `> battery` |
| `valve on` | Mở van | `> valve on` |
| `valve off` | Đóng van | `> valve off` |
| `mode auto` | Chuyển chế độ tự động | `> mode auto` |
| `mode manual` | Chuyển chế độ thủ công | `> mode manual` |
| `threshold set <val>` | Đặt ngưỡng | `> threshold set 8.0` |
| `status` | Hiển thị trạng thái hệ thống | `> status` |
| `nodes` | Liệt kê node trong mạng | `> nodes` |
| `help` | Danh sách lệnh | `> help` |

### Thêm Custom CLI

```c
// Trong ZAP, thêm custom CLI commands
void customCommandFlowPrint(void) {
    emberAfAppPrintln("Current flow: %.1f L/min", currentFlow);
}

void customCommandValveControl(void) {
    uint8_t state = emberUnsignedCommandArgument(0);
    sendValveCommand(state);
}
```

## 🤖 Logic điều khiển nâng cao

### Hysteresis (chống rung)

```c
#define HYSTERESIS 0.5  // L/min

void checkAutoControlWithHysteresis(float flow) {
    if (!autoMode) return;
    
    // Close valve với hysteresis
    if (flow > MAX_FLOW_THRESHOLD + HYSTERESIS) {
        if (valveState == true) {
            sendValveCommand(false);
        }
    }
    
    // Open valve với hysteresis
    if (flow < MIN_FLOW_THRESHOLD - HYSTERESIS) {
        if (valveState == false) {
            sendValveCommand(true);
        }
    }
}
```

### Moving Average Filter

```c
#define FILTER_SIZE 5
float flowBuffer[FILTER_SIZE] = {0};
uint8_t bufferIndex = 0;

float filterFlow(float newValue) {
    flowBuffer[bufferIndex] = newValue;
    bufferIndex = (bufferIndex + 1) % FILTER_SIZE;
    
    float sum = 0;
    for (int i = 0; i < FILTER_SIZE; i++) {
        sum += flowBuffer[i];
    }
    
    return sum / FILTER_SIZE;
}
```

### Timeout Protection

```c
#define VALVE_OPEN_TIMEOUT_MS (30 * 60 * 1000)  // 30 phút

sl_sleeptimer_timer_handle_t valveTimer;

void onValveTimeout(sl_sleeptimer_timer_handle_t *handle, void *data) {
    emberAfAppPrintln("Valve timeout - auto closing");
    sendValveCommand(false);
}

void sendValveCommandWithTimeout(bool state) {
    sendValveCommand(state);
    
    if (state == true) {
        sl_sleeptimer_start_timer_ms(
            &valveTimer,
            VALVE_OPEN_TIMEOUT_MS,
            onValveTimeout,
            NULL,
            0,
            0
        );
    } else {
        sl_sleeptimer_stop_timer(&valveTimer);
    }
}
```

## 🧪 Testing và Debug

### Test Cases

1. **Network Formation:**
   - Coordinator tạo network thành công
   - Sensor và Actuator join được

2. **Data Reception:**
   - Nhận flow report từ Sensor
   - Hiển thị đúng trên LCD/UART

3. **Auto Control:**
   - Flow > threshold → van đóng
   - Flow < threshold → van mở
   - Hysteresis hoạt động đúng

4. **Manual Control:**
   - Button → điều khiển van
   - CLI command → điều khiển van
   - Mode switch hoạt động

### CLI Debug Commands

```bash
# Network info
info
plugin network-creator status

# Node table
plugin network-creator-security open-network

# Check bindings
option binding-table print

# Network discovery
plugin network-steering start 0

# Force report request
zcl global read 0x000C 0x0055
send <nodeId> 1 1
```

