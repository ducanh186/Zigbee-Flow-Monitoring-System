/***************************************************************************//**
 * @file app.c
 * @brief Zigbee Sensor Node (Sleepy End Device) - EVENT-BASED VERSION
 *  - HW RESET pin boot: LEAVE -> wait NETWORK_DOWN -> STEERING JOIN
 *  - Joined: send Flow periodically using sl_zigbee_event (NOT tick-based!)
 *  - Battery: update random 70..100 every 30s, report only if changed
 *  - Sleep: Device enters EM2 between sends, radio OFF
 * 
 * CHANGES FROM ORIGINAL:
 *  - Removed tick-based telemetry logic
 *  - Added sl_zigbee_event for telemetry and battery
 *  - Event-driven wake -> send -> sleep cycle
 ******************************************************************************/

#include "app/framework/include/af.h"
#include "network-steering.h"
#include "zap-id.h"
#include "stack/include/ember.h"

// LED control for power saving
#include "sl_simple_led_instances.h"

// GPIO for direct hardware control
#include "em_gpio.h"

// Board control (for LCD/Display if present)
#ifdef SL_CATALOG_BOARD_CONTROL_PRESENT
#include "sl_board_control.h"
#endif

// MX25 Flash shutdown (if present)
#ifdef SL_CATALOG_MX25_FLASH_SHUTDOWN_PRESENT
#include "sl_mx25_flash_shutdown.h"
#endif

// -----------------------------------------------------------------------------
// Reset-cause compatibility (some SDKs name it RESET_EXTERNAL, some RESET_EXTERNAL_PIN)
#ifndef RESET_EXTERNAL_PIN
  #ifdef RESET_EXTERNAL
    #define RESET_EXTERNAL_PIN RESET_EXTERNAL
  #endif
#endif

// Fallback defines (build stable even if autogen issues)
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

// EVENT-BASED intervals (replaces tick-based random)
// Telemetry every 7 seconds (within 5-10s spec)
#define TELEMETRY_INTERVAL_MS   7000u

// Battery update every 30s
#define BATTERY_UPDATE_MS       30000u

// Rejoin backoff
#define REJOIN_BACKOFF_START_MS  5000u
#define REJOIN_BACKOFF_MAX_MS    60000u

// ===== EVENTS (sleep-compatible) =====
static sl_zigbee_event_t telemetryEvent;
static sl_zigbee_event_t batteryEvent;

// Event handlers - forward declarations
static void telemetryEventHandler(sl_zigbee_event_t *event);
static void batteryEventHandler(sl_zigbee_event_t *event);

// ===== STATE =====
static bool joined = false;
static bool steeringInProgress = false;

static uint16_t flowCur = 0;
static uint16_t flowLastSent = 0;

static uint8_t  battCur = 85;         // %
static uint8_t  battLastSent = 0;

// Rejoin scheduling
static uint32_t rejoinNextTick = 0;
static uint32_t rejoinBackoffMs = REJOIN_BACKOFF_START_MS;

// ===== RESET -> LEAVE -> JOIN flow (HW RESET pin) =====
static bool bootLeaveJoinArmed = false;     // true only when reset-pin boot & has stored network
static bool bootLeaveIssued = false;        // we already called emberLeaveNetwork()
static bool startSteeringPending = false;   // request to call steering from main tick (safe context)

// ===== FLOW WAVE (demo pattern) =====
static const uint16_t flowWave[] = { 0, 15, 55, 65, 80 };
#define FLOW_WAVE_LEN (sizeof(flowWave) / sizeof(flowWave[0]))
static uint8_t flowIdx = 0;   // index in flowWave
static int8_t  flowDir = 1;   // +1 up, -1 down

// ===== POWER SAVING HELPERS =====
/**
 * @brief Turn on LED to indicate device is awake/transmitting
 */
static void indicateAwake(void)
{
  sl_led_turn_on(&sl_led_led0);
}

/**
 * @brief Turn off LED to indicate device is going to sleep
 */
static void indicateSleep(void)
{
  sl_led_turn_off(&sl_led_led0);
}

/**
 * @brief Disable all peripherals for EM2 deep sleep
 *        - LCD/Display OFF
 *        - SPI Flash in shutdown mode  
 *        - VCOM disabled (via config)
 */
static void prepareForDeepSleep(void)
{
  // 1. Disable Display via board control (if available)
#ifdef SL_CATALOG_BOARD_CONTROL_PRESENT
  sl_board_disable_display();
#endif

  // 2. Directly turn off display enable pin (PD15 on most boards)
  //    This ensures LCD is OFF even if board_control doesn't work
  GPIO_PinModeSet(gpioPortD, 15, gpioModePushPull, 0);  // Display enable LOW
  
  // 3. Shutdown SPI Flash to save power
#ifdef SL_CATALOG_MX25_FLASH_SHUTDOWN_PRESENT
  sl_mx25_flash_shutdown();
#endif

  emberAfCorePrintln("Peripherals disabled for EM2");
}

// ===== HELPERS =====
static uint32_t msTick(void)
{
  return halCommonGetInt32uMillisecondTick();
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

// Flow follows array: 0 -> 15 -> 55 -> 65 -> 80 -> 65 -> 55 -> 15 -> 0 -> ...
static void updateFlow(void)
{
  if (FLOW_WAVE_LEN == 0) {
    flowCur = 0;
    return;
  }

  flowCur = flowWave[flowIdx];

  if (FLOW_WAVE_LEN < 2) return;

  // bounce next index
  if (flowDir > 0) {
    if (flowIdx >= (FLOW_WAVE_LEN - 1)) {
      flowDir = -1;
      flowIdx--;
    } else {
      flowIdx++;
    }
  } else {
    if (flowIdx == 0) {
      flowDir = 1;
      flowIdx++;
    } else {
      flowIdx--;
    }
  }
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
      ZCL_BATTERY_PERCENTAGE_REMAINING_ATTRIBUTE_ID,
      ZCL_INT8U_ATTRIBUTE_TYPE,
      halfPercent);

  emberAfSetCommandEndpoints(SENSOR_EP, COORD_EP_TELEM);
  EmberStatus st = emberAfSendCommandUnicast(EMBER_OUTGOING_DIRECT, COORD_NODE_ID);
  emberAfCorePrintln("TX batt=%u%% st=0x%02X", percent, st);
}

// ===== EVENT HANDLERS (SLEEP-COMPATIBLE) =====

/**
 * @brief Telemetry event handler - called every TELEMETRY_INTERVAL_MS
 *        Device wakes from EM2, sends flow, re-schedules, then sleeps again
 */
static void telemetryEventHandler(sl_zigbee_event_t *event)
{
  if (!joined) {
    return;
  }

  // *** LED ON - indicate awake/transmitting ***
  indicateAwake();

  // Update and send flow
  updateFlow();
  sendFlowReport(flowCur);
  flowLastSent = flowCur;

  // *** LED OFF - going back to sleep ***
  indicateSleep();

  // Re-schedule for next wake
  sl_zigbee_event_set_delay_ms(event, TELEMETRY_INTERVAL_MS);
}

/**
 * @brief Battery event handler - called every BATTERY_UPDATE_MS
 *        Updates battery level and sends report only if changed
 */
static void batteryEventHandler(sl_zigbee_event_t *event)
{
  if (!joined) {
    return;
  }

  // Random 70..100
  battCur = (uint8_t)((halCommonGetRandom() % 31) + 70);

  // Send only if changed
  if (battCur != battLastSent) {
    // *** LED ON - indicate awake/transmitting ***
    indicateAwake();

    sendBatteryReport(battCur);
    battLastSent = battCur;

    // *** LED OFF - going back to sleep ***
    indicateSleep();
  }

  // Re-schedule
  sl_zigbee_event_set_delay_ms(event, BATTERY_UPDATE_MS);
}

// ===== CALLBACKS =====
void emberAfMainInitCallback(void)
{
  uint8_t baseResetInfo = halGetResetInfo();

  bool extReset = false;
#ifdef RESET_EXTERNAL_PIN
  extReset = (baseResetInfo == RESET_EXTERNAL_PIN);
#endif

  EmberNetworkStatus ns = emberNetworkState();

  emberAfCorePrintln("Sensor init: resetInfo=0x%02X extReset=%d ns=%d",
                     baseResetInfo, extReset ? 1 : 0, ns);

  // *** POWER SAVING: Prepare for EM2 deep sleep ***
  indicateSleep();          // LED OFF
  prepareForDeepSleep();    // LCD OFF, Flash shutdown

  bootLeaveJoinArmed = false;
  bootLeaveIssued = false;
  startSteeringPending = false;

  joined = false;
  steeringInProgress = false;

  rejoinNextTick = 0;
  rejoinBackoffMs = REJOIN_BACKOFF_START_MS;

  // Initialize events (sleep-compatible)
  sl_zigbee_event_init(&telemetryEvent, telemetryEventHandler);
  sl_zigbee_event_init(&batteryEvent, batteryEventHandler);

  // If HW reset pin AND we have stored network => LEAVE first, then steering join
  if (extReset && ns != EMBER_NO_NETWORK) {
    bootLeaveJoinArmed = true;

    emberAfCorePrintln("HW RESET pin -> LEAVE first");

    EmberStatus st = emberLeaveNetwork();

    if (st == EMBER_SUCCESS) {
      bootLeaveIssued = true;
      return; // wait for NETWORK_DOWN then start steering from main tick
    } else {
      bootLeaveJoinArmed = false;
      startSteeringPending = true;
    }
  } else {
    startSteeringPending = true;
  }
}

void emberAfStackStatusCallback(EmberStatus status)
{
  emberAfCorePrintln("Stack status: 0x%02X", status);

  if (status == EMBER_NETWORK_UP) {
    joined = true;
    steeringInProgress = false;

    emberAfCorePrintln("Joined! Sleepy mode active.");

    // *** Ensure LED is OFF after joining ***
    indicateSleep();

    // reset rejoin backoff
    rejoinBackoffMs = REJOIN_BACKOFF_START_MS;
    rejoinNextTick = 0;

    // reset demo wave
    flowIdx = 0;
    flowDir = 1;
    flowCur = flowWave[0];
    flowLastSent = flowCur;
    battLastSent = battCur;

    // *** START EVENTS *** 
    // First telemetry after 2s (allow network to stabilize)
    sl_zigbee_event_set_delay_ms(&telemetryEvent, 2000);
    // First battery after 5s
    sl_zigbee_event_set_delay_ms(&batteryEvent, 5000);

  } else if (status == EMBER_NETWORK_DOWN) {
    joined = false;

    // *** Ensure LED is OFF ***
    indicateSleep();

    // *** STOP EVENTS *** when disconnected
    sl_zigbee_event_set_inactive(&telemetryEvent);
    sl_zigbee_event_set_inactive(&batteryEvent);

    // If we intentionally left due to HW reset pin, start steering
    if (bootLeaveIssued) {
      bootLeaveIssued = false;
      startSteeringPending = true;
      return;
    }

    // Normal down: schedule rejoin with backoff
    if (!steeringInProgress && rejoinNextTick == 0) {
      scheduleRejoin();
    }
  }
}

/**
 * @brief Main tick callback - MINIMAL VERSION for sleepy device
 *        Only handles network steering/rejoin, NO telemetry logic!
 *        Telemetry is handled by event system which is sleep-compatible.
 */
void emberAfMainTickCallback(void)
{
  uint32_t now = msTick();

  // ---- Start steering from safe context (main tick), not stack status callback
  if (!joined && startSteeringPending && !steeringInProgress) {
    startSteeringPending = false;
    steeringInProgress = true;

    // equivalent CLI "start 0"
    sli_zigbee_af_network_steering_options_mask =
        EMBER_AF_PLUGIN_NETWORK_STEERING_OPTIONS_NONE;

    emberAfCorePrintln("Steering start (like: plugin network-steering start 0) ...");
    EmberStatus st = emberAfPluginNetworkSteeringStart();
    emberAfCorePrintln("Steering start: 0x%02X", st);

    if (st != EMBER_SUCCESS) {
      steeringInProgress = false;
      if (rejoinNextTick == 0) scheduleRejoin();
    }
    return;
  }

  // Not joined: rejoin only when time comes (avoid tight loop)
  if (!joined) {
    if (!steeringInProgress && rejoinNextTick != 0 && now >= rejoinNextTick) {
      emberAfCorePrintln("Rejoin now...");
      steeringInProgress = true;
      rejoinNextTick = 0;

      sli_zigbee_af_network_steering_options_mask =
          EMBER_AF_PLUGIN_NETWORK_STEERING_OPTIONS_NONE;

      EmberStatus st = emberAfPluginNetworkSteeringStart();
      emberAfCorePrintln("Steering start: 0x%02X", st);

      if (st != EMBER_SUCCESS) {
        steeringInProgress = false;
        if (rejoinNextTick == 0) scheduleRejoin();
      }
    }
    return;
  }

  // *** TELEMETRY LOGIC REMOVED ***
  // All telemetry is now handled by sl_zigbee_event which is sleep-compatible.
  // Device will sleep between events, waking only to send and poll.
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
    if (rejoinNextTick == 0) scheduleRejoin();
  }
}

void emberAfRadioNeedsCalibratingCallback(void)
{
  sl_mac_calibrate_current_channel();
}

// ===== DEBUG HELPERS (optional) =====
#if 0  // Enable if needed for debugging
/**
 * @brief Force device to stay awake (for debugging via CLI)
 */
void debugForceWake(void)
{
  emberAfForceEndDeviceToStayAwake(true);
  emberAfCorePrintln("Debug: Force stay awake ENABLED");
}

/**
 * @brief Allow device to sleep normally
 */
void debugAllowSleep(void)
{
  emberAfForceEndDeviceToStayAwake(false);
  emberAfCorePrintln("Debug: Sleep ALLOWED");
}
#endif
