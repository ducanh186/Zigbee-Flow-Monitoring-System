#include "app_config.h"
#include "app_state.h"
#include "app_utils.h"
#include "app_log.h"
#include "net_mgr.h"
#include "lcd_ui.h"

#include "sl_simple_button.h"
#include "sl_simple_button_instances.h"
#include "sl_simple_led_instances.h"  // For LED toggle in ISR debug
#include "sl_iostream.h"              // For direct UART output
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
  // DEBUG: Toggle LED to confirm ISR is called (safe in ISR)
  sl_led_toggle(&sl_led_led0);
  
  sl_button_state_t st = sl_button_get_state(handle);

  // ========== PB0 ==========
  if (handle == &sl_button_btn0) {
    if (st == SL_SIMPLE_BUTTON_PRESSED) {
      g_pb0PressTick = msTick();
      // DEBUG: Set short pending immediately on press for testing
      g_pb0ShortPending = true;
      return;
    }
    if (st == SL_SIMPLE_BUTTON_RELEASED) {
      uint32_t dt = msTick() - g_pb0PressTick;
      if (dt >= PB0_LONG_PRESS_MS) {
        g_pb0LongPending = true;  // Defer to main loop
        g_pb0ShortPending = false; // Cancel short
      }
      // Short already set on PRESSED
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
  // Read volatile flags once into local vars (atomic read)
  bool shortPend = g_pb0ShortPending;
  bool longPend = g_pb0LongPending;
  bool pb1Pend = g_pb1Pending;
  
  // Debug: Check if any button flag is pending - use direct UART
  if (shortPend || longPend || pb1Pend) {
    // Try direct stdout write
    sl_iostream_printf(SL_IOSTREAM_STDOUT, "[BTN] flags: s=%d l=%d p=%d\r\n", 
                       shortPend, longPend, pb1Pend);
  }

  // PB0 Long press: Toggle between IDE Mode and Dashboard Mode
  if (longPend) {
    g_pb0LongPending = false;
    sl_iostream_printf(SL_IOSTREAM_STDOUT, "[BTN] PB0 long\r\n");
    g_uartGatewayEnabled = !g_uartGatewayEnabled;
    
    if (g_uartGatewayEnabled) {
#ifdef DEBUG_NET_PRINTS
      emberAfCorePrintln("");
      emberAfCorePrintln("========================================");
      emberAfCorePrintln("  DASHBOARD MODE - @DATA enabled");
      emberAfCorePrintln("  Use: json {\"id\":1,\"op\":\"info\"}");
      emberAfCorePrintln("========================================");
#endif
      lcd_ui_set_network("DASHBOARD");
      appLogLog("BTN", "mode_switch", "\"mode\":\"dashboard\"");
    } else {
#ifdef DEBUG_NET_PRINTS
      emberAfCorePrintln("");
      emberAfCorePrintln("========================================");
      emberAfCorePrintln("  IDE MODE - SDK CLI commands");
      emberAfCorePrintln("  Type 'help' to see all commands");
      emberAfCorePrintln("========================================");
#endif
      lcd_ui_set_network("IDE MODE");
      appLogLog("BTN", "mode_switch", "\"mode\":\"ide\"");
    }
  }

  // PB0 Short press: Form network
  if (shortPend) {
    g_pb0ShortPending = false;
    sl_iostream_printf(SL_IOSTREAM_STDOUT, "[BTN] PB0 short\r\n");
    (void)netMgrRequestForm(g_netCfg, "pb0", false);
  }

  // PB1: Open network for joining
  if (pb1Pend) {
    g_pb1Pending = false;
    sl_iostream_printf(SL_IOSTREAM_STDOUT, "[BTN] PB1\r\n");
    
    if (emberAfNetworkState() != EMBER_JOINED_NETWORK) {
      emberAfCorePrintln("[BTN] PB1: Not in network");
      appLogLog("BTN", "pb1_open", "\"error\":\"not_in_network\"");
      lcd_ui_set_network("NET: NO NWK");
      return;
    }

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
    EmberStatus st = emberAfPluginNetworkCreatorSecurityOpenNetwork();
#ifdef DEBUG_NET_PRINTS
    emberAfCorePrintln("PB1: Open network: 0x%02X", st);
#endif
    
    if (st == EMBER_SUCCESS) {
      appLogLog("BTN", "pb1_open", "\"status\":\"opened\"");
      lcd_ui_set_network("NET: JOINING");
    } else {
      appLogLog("BTN", "pb1_open", "\"status\":\"failed\",\"zstatus\":\"0x%02X\"", (unsigned)st);
    }
#else
#ifdef DEBUG_NET_PRINTS
    emberAfCorePrintln("PB1: network-creator-security not present");
#endif
    appLogLog("BTN", "pb1_open", "\"error\":\"plugin_missing\"");
#endif
  }
}
