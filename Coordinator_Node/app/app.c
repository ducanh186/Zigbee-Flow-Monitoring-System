#include "app_config.h"
#include "app_state.h"
#include "app_log.h"
#include "uart_link.h"
#include "net_mgr.h"
#include "valve_ctrl.h"
#include "lcd_ui.h"
#include "buttons.h"
#include "cli_commands.h"
#include "app/framework/include/af.h"

// Periodic @DATA output for Dashboard
#define DATA_REPORT_INTERVAL_MS  5000   // Send @DATA every 5 seconds (was 2s)
#define DATA_FORCE_INTERVAL_MS   30000  // Force send even if unchanged every 30s
static uint32_t s_lastDataReport = 0;
static uint32_t s_lastForceReport = 0;

// Track last sent values to detect changes
static uint16_t s_lastSentFlow = 0xFFFF;
static uint8_t  s_lastSentBattery = 0xFF;
static bool     s_lastSentValve = false;
static app_mode_t s_lastSentMode = MODE_AUTO;

void emberAfMainInitCallback(void)
{
  // Register custom CLI commands (json, info, data)
  customCliInit();
  
  bool lcdOk = lcdUiInit();
  emberAfCorePrintln("APP: lcdUiInit() returned %d", lcdOk);

  appStateInit();
  appStateNotifyChanged();

  // Set initial LCD values
  lcd_ui_set_flow(g_flow);
  lcd_ui_set_battery(g_batteryPercent);
  lcd_ui_set_valve(valveCtrlIsOpen());
  lcd_ui_set_network("STARTING");

  emberAfCorePrintln("Coordinator init, netState=%d", emberAfNetworkState());
  appLogInfo();
  appLogData();
  
  s_lastDataReport = halCommonGetInt32uMillisecondTick();
}

void emberAfMainTickCallback(void)
{
  uint32_t now = halCommonGetInt32uMillisecondTick();

  // 0) Process button actions (deferred from ISR)
  buttonsTick();

  // 1) LCD rendering (non-blocking, only when dirty)
  lcd_ui_process();

  // 2) UART gateway - ONLY poll in Dashboard Mode
  //    In IDE Mode, let CLI handle UART input
  if (g_uartGatewayEnabled) {
    uartLinkPoll();
  }

  // 3) Network manager
  netMgrTick();

  // 4) Periodic @DATA output for Dashboard
  //    - Only send if data changed OR force interval passed
  //    - Reduces UART spam when data is static (e.g., no sensor connected)
  if (g_uartGatewayEnabled && (now - s_lastDataReport) >= DATA_REPORT_INTERVAL_MS) {
    s_lastDataReport = now;
    
    // Check if any value changed
    bool valveNow = valveCtrlIsOpen();
    bool dataChanged = (g_flow != s_lastSentFlow) ||
                       (g_batteryPercent != s_lastSentBattery) ||
                       (valveNow != s_lastSentValve) ||
                       (g_mode != s_lastSentMode);
    
    // Force send periodically even if unchanged (heartbeat)
    bool forceReport = (now - s_lastForceReport) >= DATA_FORCE_INTERVAL_MS;
    
    if (dataChanged || forceReport) {
      appLogData();
      
      // Update last sent values
      s_lastSentFlow = g_flow;
      s_lastSentBattery = g_batteryPercent;
      s_lastSentValve = valveNow;
      s_lastSentMode = g_mode;
      
      if (forceReport) {
        s_lastForceReport = now;
      }
    }
  }
}

void emberAfRadioNeedsCalibratingCallback(void)
{
  //sl_mac_calibrate_current_channel();
}
