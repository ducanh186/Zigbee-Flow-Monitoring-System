#include "app_config.h"
#include "app_state.h"
#include "app_utils.h"
#include "app_log.h"
#include "net_mgr.h"
#include "lcd_ui.h"

#include "sl_simple_button.h"
#include "sl_simple_button_instances.h"
#include "app/framework/include/af.h"

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
#include "network-creator-security.h"
#endif

// Open network duration when PB1 pressed (seconds)
#define PB1_OPEN_NETWORK_SEC  180

// Debounce time for PB1 (ms) - prevent repeated triggers while held
#define PB1_DEBOUNCE_MS       2000

static uint32_t g_pb0PressTick = 0;
static uint32_t g_pb1LastTriggerTick = 0;  // Track last PB1 action time

// ========== DEFERRED ACTION FLAGS ==========
// ISR cannot call Zigbee stack functions directly!
// Set flags here, process in buttonsTick() from main loop
static volatile bool g_pb0ShortPending = false;
static volatile bool g_pb0LongPending = false;
static volatile bool g_pb1Pending = false;

// Called from ISR - ONLY set flags, no stack calls!
void sl_button_on_change(const sl_button_t *handle)
{
  sl_button_state_t st = sl_button_get_state(handle);

  // ========== PB0 ==========
  if (handle == &sl_button_btn0) {
    if (st == SL_SIMPLE_BUTTON_PRESSED) {
      g_pb0PressTick = msTick();
      return;
    }
    if (st == SL_SIMPLE_BUTTON_RELEASED) {
      uint32_t dt = msTick() - g_pb0PressTick;
      if (dt >= PB0_LONG_PRESS_MS) {
        g_pb0LongPending = true;  // Defer to main loop
      } else {
        g_pb0ShortPending = true; // Defer to main loop
      }
      return;
    }
  }

  // ========== PB1 ==========
  // Only trigger on PRESSED, and only if debounce time has passed
  if (handle == &sl_button_btn1) {
    if (st == SL_SIMPLE_BUTTON_PRESSED) {
      uint32_t now = msTick();
      // Debounce: ignore if triggered recently
      if ((now - g_pb1LastTriggerTick) >= PB1_DEBOUNCE_MS) {
        g_pb1Pending = true;  // Defer to main loop
        g_pb1LastTriggerTick = now;
      }
      return;
    }
  }
}

// Called from main loop (emberAfMainTickCallback) - safe to call stack functions
void buttonsTick(void)
{
  // PB0 Long press: Toggle between IDE Mode and Dashboard Mode
  if (g_pb0LongPending) {
    g_pb0LongPending = false;
    g_uartGatewayEnabled = !g_uartGatewayEnabled;
    
    if (g_uartGatewayEnabled) {
      emberAfCorePrintln("");
      emberAfCorePrintln("========================================");
      emberAfCorePrintln("  DASHBOARD MODE - @DATA enabled");
      emberAfCorePrintln("  Use: json {\"id\":1,\"op\":\"info\"}");
      emberAfCorePrintln("========================================");
      lcd_ui_set_network("DASHBOARD");
      appLogLog("mode_switch", "pb0_long", "DASHBOARD");
    } else {
      emberAfCorePrintln("");
      emberAfCorePrintln("========================================");
      emberAfCorePrintln("  IDE MODE - SDK CLI commands");
      emberAfCorePrintln("  Type 'help' to see all commands");
      emberAfCorePrintln("========================================");
      lcd_ui_set_network("IDE MODE");
      appLogLog("mode_switch", "pb0_long", "IDE");
    }
  }

  // PB0 Short press: Form network
  if (g_pb0ShortPending) {
    g_pb0ShortPending = false;
    emberAfCorePrintln("PB0 short: Request form network");
    (void)netMgrRequestForm(g_netCfg, "pb0", false);
  }

  // PB1: Open network for joining
  if (g_pb1Pending) {
    g_pb1Pending = false;
    
    if (emberAfNetworkState() != EMBER_JOINED_NETWORK) {
      emberAfCorePrintln("PB1: Not in network, cannot open");
      appLogLog("net_open", "pb1", "not_in_network");
      lcd_ui_set_network("NET: NO NWK");
      return;
    }

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
    EmberStatus st = emberAfPluginNetworkCreatorSecurityOpenNetwork();
    emberAfCorePrintln("PB1: Open network: 0x%02X", st);
    
    if (st == EMBER_SUCCESS) {
      appLogLog("net_open", "pb1", "opened");
      lcd_ui_set_network("NET: JOINING");
    } else {
      appLogLog("net_open", "pb1", "failed");
    }
#else
    emberAfCorePrintln("PB1: network-creator-security not present");
    appLogLog("net_open", "pb1", "plugin_missing");
#endif
  }
}
