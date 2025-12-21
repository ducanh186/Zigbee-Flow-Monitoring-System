#include "app/framework/include/af.h"
#include "network-steering.h"
#include "zap-id.h"
#include "stack/include/ember.h"

// Fallback defines (để build chắc chắn ngay cả khi autogen trục trặc)
#ifndef ZCL_POWER_CONFIGURATION_CLUSTER_ID
#define ZCL_POWER_CONFIGURATION_CLUSTER_ID 0x0001
#endif

#ifndef ZCL_BATTERY_PERCENTAGE_REMAINING_ATTRIBUTE_ID
#define ZCL_BATTERY_PERCENTAGE_REMAINING_ATTRIBUTE_ID 0x0021
#endif

#ifndef ZCL_FLOW_MEASUREMENT_CLUSTER_ID
#define ZCL_FLOW_MEASUREMENT_CLUSTER_ID 0x0404
#endif

#ifndef ZCL_REPORT_ATTRIBUTES_COMMAND_ID
#define ZCL_REPORT_ATTRIBUTES_COMMAND_ID 0x0A
#endif

// ===== CONFIG =====
#define SENSOR_EP            1
#define COORD_EP_TELEM       1
#define COORD_NODE_ID        0x0000

// Gửi/kiểm tra mỗi 5s (demo wave)
#define TICK_MS              5000u

// (Giữ lại cho khỏi warning/đỡ sửa nhiều file)
#define FLOW_SEND_DELTA      ((uint16_t)5)

// Battery update mỗi 30s
#define BATTERY_SEND_MS      30000u

// Rejoin backoff
#define REJOIN_BACKOFF_START_MS  5000u
#define REJOIN_BACKOFF_MAX_MS    60000u

// ===== STATE =====
static bool joined = false;
static bool steeringInProgress = false;

static uint32_t lastTick = 0;

static uint16_t flowCur = 0;
static uint16_t flowLastSent = 0;

static uint8_t  battCur = 85;         // %
static uint8_t  battLastSent = 0;
static uint32_t lastBattUpdate = 0;

// Rejoin scheduling
static uint32_t rejoinNextTick = 0;
static uint32_t rejoinBackoffMs = REJOIN_BACKOFF_START_MS;

// ===== FLOW WAVE (demo pattern) =====
static const uint16_t flowWave[] = { 0, 15, 55, 65, 80 };
#define FLOW_WAVE_LEN (sizeof(flowWave) / sizeof(flowWave[0]))
static uint8_t flowIdx = 0;   // index trong flowWave
static int8_t  flowDir = 1;   // +1 đi lên, -1 đi xuống

// ===== HELPERS =====
static uint32_t msTick(void)
{
  return halCommonGetInt32uMillisecondTick();
}

static uint16_t absDiffU16(uint16_t a, uint16_t b)
{
  return (a > b) ? (a - b) : (b - a);
}

static uint16_t clamp_u16(int v, int lo, int hi)
{
  if (v < lo) return (uint16_t)lo;
  if (v > hi) return (uint16_t)hi;
  return (uint16_t)v;
}

static void scheduleRejoin(void)
{
  uint32_t now = msTick();
  rejoinNextTick = now + rejoinBackoffMs;

  emberAfCorePrintln("Rejoin scheduled in %lu ms",
                     (unsigned long)(rejoinNextTick - now));

  // exponential backoff: 5s -> 10s -> 20s -> 40s -> 60s (cap)
  if (rejoinBackoffMs < REJOIN_BACKOFF_MAX_MS) {
    rejoinBackoffMs *= 2;
    if (rejoinBackoffMs > REJOIN_BACKOFF_MAX_MS) {
      rejoinBackoffMs = REJOIN_BACKOFF_MAX_MS;
    }
  }
}

// Flow theo mảng: 0 -> 15 -> 55 -> 65 -> 80 -> 65 -> 55 -> 15 -> 0 -> ...
static void updateFlow(void)
{
  if (FLOW_WAVE_LEN == 0) {
    flowCur = 0;
    return;
  }

  // lấy giá trị hiện tại
  flowCur = flowWave[flowIdx];

  if (FLOW_WAVE_LEN < 2) return;

  // chuẩn bị index cho lần sau (bounce)
  if (flowDir > 0) {
    if (flowIdx >= (FLOW_WAVE_LEN - 1)) {
      flowDir = -1;
      flowIdx--;     // quay đầu từ last về last-1
    } else {
      flowIdx++;
    }
  } else {
    if (flowIdx == 0) {
      flowDir = 1;
      flowIdx++;     // quay đầu từ 0 lên 1
    } else {
      flowIdx--;
    }
  }
}

static void updateBatteryIfNeeded(void)
{
  uint32_t now = msTick();
  if (now - lastBattUpdate < BATTERY_SEND_MS) return;
  lastBattUpdate = now;

  // random 70..100
  battCur = (uint8_t)((halCommonGetRandom() % 31) + 70);
}

static void sendFlowReport(uint16_t value)
{
  emberAfFillExternalBuffer(
      (ZCL_GLOBAL_COMMAND | ZCL_FRAME_CONTROL_SERVER_TO_CLIENT),
      ZCL_FLOW_MEASUREMENT_CLUSTER_ID,
      ZCL_REPORT_ATTRIBUTES_COMMAND_ID,
      "vuv",                   // attrId(u16), type(u8), value(u16)
      0x0000,                  // MeasuredValue
      ZCL_INT16U_ATTRIBUTE_TYPE,
      value);

  emberAfSetCommandEndpoints(SENSOR_EP, COORD_EP_TELEM);
  EmberStatus st = emberAfSendCommandUnicast(EMBER_OUTGOING_DIRECT, COORD_NODE_ID);
  emberAfCorePrintln("TX flow=%u st=0x%02X", value, st);
}

static void sendBatteryReport(uint8_t percent)
{
  uint8_t halfPercent = (uint8_t)(percent * 2);  // 0.5% unit

  emberAfFillExternalBuffer(
      (ZCL_GLOBAL_COMMAND | ZCL_FRAME_CONTROL_SERVER_TO_CLIENT),
      ZCL_POWER_CONFIGURATION_CLUSTER_ID,
      ZCL_REPORT_ATTRIBUTES_COMMAND_ID,
      "vuu",                  // attrId(u16), type(u8), value(u8)
      ZCL_BATTERY_PERCENTAGE_REMAINING_ATTRIBUTE_ID, // 0x0021
      ZCL_INT8U_ATTRIBUTE_TYPE,
      halfPercent);

  emberAfSetCommandEndpoints(SENSOR_EP, COORD_EP_TELEM);
  EmberStatus st = emberAfSendCommandUnicast(EMBER_OUTGOING_DIRECT, COORD_NODE_ID);
  emberAfCorePrintln("TX batt=%u%% st=0x%02X", percent, st);
}

// ===== CALLBACKS =====
void emberAfMainInitCallback(void)
{
  emberAfCorePrintln("Sensor init -> start steering");
  steeringInProgress = true;

  EmberStatus st = emberAfPluginNetworkSteeringStart();
  emberAfCorePrintln("Steering start: 0x%02X", st);
}

void emberAfStackStatusCallback(EmberStatus status)
{
  emberAfCorePrintln("Stack status: 0x%02X", status);

  if (status == EMBER_NETWORK_UP) {
    joined = true;
    steeringInProgress = false;

    // Non-sleepy ED: giữ RX ON khi idle để demo ổn định
    emberZllSetRxOnWhenIdle(true);
    emberAfCorePrintln("RxOnWhenIdle = 1 (non-sleepy ED)");

    // reset timers
    lastTick = msTick();
    lastBattUpdate = msTick();

    // reset rejoin backoff
    rejoinBackoffMs = REJOIN_BACKOFF_START_MS;
    rejoinNextTick = 0;

    // reset demo wave về 0
    flowIdx = 0;
    flowDir = 1;
    flowCur = flowWave[0];
    flowLastSent = flowCur;

  } else if (status == EMBER_NETWORK_DOWN) {
    joined = false;

    // Không gọi steering liên tục -> schedule rejoin
    if (!steeringInProgress && rejoinNextTick == 0) {
      scheduleRejoin();
    }
  }
}

void emberAfMainTickCallback(void)
{
  uint32_t now = msTick();

  // Nếu chưa join: chỉ rejoin khi đến giờ (tránh loop)
  if (!joined) {
    if (!steeringInProgress && rejoinNextTick != 0 && now >= rejoinNextTick) {
      emberAfCorePrintln("Rejoin now...");
      steeringInProgress = true;
      rejoinNextTick = 0;

      EmberStatus st = emberAfPluginNetworkSteeringStart();
      emberAfCorePrintln("Steering start: 0x%02X", st);
    }
    return;
  }

  // Joined rồi: mỗi 5s mới send
  if (now - lastTick < TICK_MS) return;
  lastTick = now;

  updateFlow();
  updateBatteryIfNeeded();

  // Demo: gửi flow mỗi 5s theo pattern 0->80->0 (unconditional)
  sendFlowReport(flowCur);
  flowLastSent = flowCur;

  // Gửi battery nếu đổi
  if (battCur != battLastSent) {
    sendBatteryReport(battCur);
    battLastSent = battCur;
  }
}

void emberAfPluginNetworkSteeringCompleteCallback(EmberStatus status,
                                                 uint8_t totalBeacons,
                                                 uint8_t joinAttempts,
                                                 uint8_t finalState)
{
  (void)totalBeacons;
  (void)joinAttempts;
  (void)finalState;

  emberAfCorePrintln("Join complete: 0x%02X", status);
  steeringInProgress = false;

  if (status != EMBER_SUCCESS) {
    // Join fail -> schedule rejoin
    if (rejoinNextTick == 0) {
      scheduleRejoin();
    }
  }
}

void emberAfRadioNeedsCalibratingCallback(void)
{
  sl_mac_calibrate_current_channel();
}
