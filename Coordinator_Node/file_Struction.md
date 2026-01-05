Nhìn cấu trúc này là bạn đang tách project theo kiểu **module (mô-đun)**: mỗi “chức năng lớn” nằm trong một cặp **header file (file header)** `.h` + **source file (file nguồn)** `.c`. Mục tiêu là dễ bảo trì, dễ debug, và tránh 1 file `app.c` phình to.

Dưới đây là “vai trò từng file” + cách chúng **chảy data / logic flow** với nhau.

---

## Bức tranh tổng thể (logic flow)

**(1) Boot / init**

* `app.c` chạy các callback init của Zigbee/AF → gọi log/info, init state, init UART…

**(2) Telemetry từ node khác → cập nhật state**

* Zigbee nhận gói (ZCL command / report) → `telemetry_rx.c` parse → cập nhật `app_state.c`

**(3) Dashboard/PC ↔ UART**

* PC gửi `@CMD {...}` → `uart_link.c` đọc line → chuyển cho `cmd_handler.c`
* `cmd_handler.c` parse JSON → gọi `valve_ctrl.c` hoặc `net_mgr.c`
* Kết quả → `app_log.c` in ra `@ACK/@LOG/@INFO/@DATA` qua UART

**(4) Điều khiển van / join callback**

* `valve_ctrl.c` xử lý logic On/Off, trust-center join callback… và có thể gọi `printInfoToPC()` để báo trạng thái lên PC

---

## Giải thích từng file

### `app.c`

**“Entry module” của ứng dụng Zigbee.**

* Chứa các callback kiểu `emberAfMainInitCallback()`, tick, event handler…
* Nhiệm vụ: gọi init cho các module khác, set cấu hình ban đầu, kick off network/steering (tùy bạn).

**Trade-off:** gọn và dễ đọc hơn, nhưng nếu bạn nhét hết logic vào đây thì nó sẽ trở thành “god file”.

---

### `app_config.h`

**Chỗ để cấu hình compile-time** (endpoint, node id coordinator, tick ms, enable/disable feature…).

* Nên để **config của app**, không nên define lại các macro “chuẩn” của Zigbee/ZCL (mấy cái sinh từ `autogen/zap-*.h`), vì dễ gây lỗi redefine như bạn gặp.

**Best practice:** chỉ define các macro *của bạn tự đặt tên*, hoặc dùng `#ifndef ... #define ... #endif` cho fallback hiếm khi cần.

---

### `app_log.h` / `app_log.c`

**Logging + “UART protocol output”** (ví dụ: `@DATA`, `@INFO`, `@ACK`, `@LOG`).

* `printInfoToPC()` thường lấy `nodeId`, `eui64`, network params… rồi in JSON.
* `appLogInfo/appLogData/appLogAck/appLogLog` là API để module khác gọi mà không cần biết chi tiết format UART.

**Trade-off:**

* Ưu: format output thống nhất, debug dễ.
* Nhược: nếu log quá nhiều có thể “spam UART” và tốn CPU.

---

### `app_state.h` / `app_state.c`

**“Single source of truth” cho trạng thái hệ thống.**
Ví dụ state có thể gồm: flow, valve_state, battery, joined/not, last_seen…

* `telemetry_rx` cập nhật state
* `app_log` đọc state để in ra `@DATA`
* `cmd_handler/valve_ctrl` thay đổi state (khi user điều khiển)

**Trade-off:**

* Ưu: dễ đồng bộ và debug (mọi thứ nhìn vào 1 chỗ).
* Nhược: phải cẩn thận “ownership” (ai được quyền ghi state), tránh ghi lung tung.

---

### `app_utils.h` / `app_utils.c`

**Các helper dùng chung**: parse string, clamp, convert EUI64 → hex string, safe buffer, random…

* Mục tiêu: tránh copy-paste.

**Trade-off:** tiện, nhưng đừng biến nó thành “sọt rác” chứa mọi thứ không biết để đâu.

---

### `app_zcl_fallback.h`

**Fallback cho ZCL IDs / constants** khi autogen thiếu hoặc bạn build lệch cấu hình.

* File này thường chỉ nên dùng khi bạn làm “portable demo”, nhưng trong project Zigbee chuẩn thì **autogen/zap-id.h** đã cung cấp đủ.

**Cảnh báo:** đây là nơi hay gây **macro redefine** → kéo theo lỗi enum “expected identifier…” (bạn từng gặp).
Nếu đã có `autogen/zap-id.h` thì ưu tiên dùng autogen, hạn chế fallback.

---

### `buttons.c`

**Xử lý nút nhấn (PB0/PB1)** → bật/tắt feature, reset/join, toggle UART gateway…

* Thường dùng callback `sl_button_on_change()`.

**Data flow:** button event → gọi `net_mgr` hoặc đổi flag trong `app_state`, rồi log qua `app_log`.

---

### `cmd_handler.h` / `cmd_handler.c`

**Command parser từ PC (UART)**.

* Nhận line `@CMD {...}` → parse JSON → route theo `"op"`:

  * `"valve_set"` → `valve_ctrl`
  * `"net_form"/"net_cfg_set"` → `net_mgr`
* Trả kết quả về `@ACK`.

**Trade-off:**

* Ưu: clean boundary giữa “protocol” và “business logic”.
* Nhược: JSON parse trên MCU phải cẩn thận memory/edge cases.

---

### `net_mgr.h` / `net_mgr.c`

**Network management**: form/join/leave/steering/channel/panId/txpower…

* Đây là nơi bọc các API như network creator / network steering.

**Forward-thinking:** nếu sau này bạn thêm “auto rejoin khi mất mạng”, “factory reset”, “leave+join on reset”… thì nên nằm ở đây.

---

### `telemetry_rx.c`

**Nhận telemetry Zigbee từ node khác** (thường qua callback `emberAfPreCommandReceivedCallback`).

* Parse `clusterId`, `commandId`, payload…
* Update `app_state` (flow/battery/valve…)
* Có thể trigger `app_logData()` để PC nhận realtime.

**Trade-off:** parse ở đây nhanh, nhưng phải cẩn thận ZCL frame format + endpoint match.

---

### `uart_link.h` / `uart_link.c`

**UART transport layer**: đọc byte từ UART, ghép thành line, detect prefix `@CMD`, push cho `cmd_handler`.

* Có thể chứa ring buffer, line buffer, timeout…

**Trade-off:**

* Ưu: tách “I/O raw” khỏi “logic parse JSON”.
* Nhược: dễ bug buffer overflow nếu không giới hạn line length.

---

### `valve_ctrl.h` / `valve_ctrl.c`

**Valve control logic + Zigbee On/Off client/server** (tùy role).

* Gửi On/Off command tới valve node, hoặc xử lý command đến.
* Chứa callback kiểu `emberAfTrustCenterJoinCallback()` → khi có node join thì log/print info.

**Trade-off:**

* Ưu: mọi thứ liên quan van gom 1 chỗ.
* Nhược: dễ bị “God module” nếu bạn nhét cả network + telemetry + UART vào đây (nên tránh).

---

### Thư mục `autogen/`

**Code sinh tự động từ Simplicity Studio / AppBuilder / ZAP**

* `zap-id.h`, `zap-type.h`, command parser, callback dispatcher…
* Bạn **không nên sửa trực tiếp** (vì regen sẽ mất).
* Đây là “nguồn chuẩn” cho ZCL cluster id / attribute type / command id.

---

## Gợi ý nhỏ để bạn debug nhanh hơn (rất thực tế)

* Nếu thấy lỗi kiểu `implicit declaration`: thường là **quên include header** hoặc header không declare hàm.
* Nếu thấy lỗi kiểu macro redefine (ZCL_…): gần như chắc chắn bạn đang **define trùng** với `autogen/zap-*.h` hoặc `af.h`.

---

Nếu bạn muốn, bạn paste nội dung ngắn của:

* `app_log.h` (phần prototype)
* `printInfoToPC()` trong `app_log.c`

Mình sẽ chỉ ra luôn: include nên nằm đâu, tránh circular include thế nào, và cách để `appLogData()` lấy đúng state (flow/valve/battery) thay vì hardcode.
