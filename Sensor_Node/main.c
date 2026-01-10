/**
 * @file main.c
 * @brief Zigbee Sleepy End Device - Main with Power Manager ENABLED
 * 
 * CHANGE: Uncommented sl_power_manager_sleep() to enable EM2/EM3 sleep
 */

#ifdef SL_COMPONENT_CATALOG_PRESENT
#include "sl_component_catalog.h"
#endif
#include "sl_system_init.h"
#if defined(SL_CATALOG_POWER_MANAGER_PRESENT)
#include "sl_power_manager.h"
#endif
#if defined(SL_CATALOG_KERNEL_PRESENT)
#include "sl_system_kernel.h"
#else
#include "sl_system_process_action.h"
#endif

void app_init(void) {}
void app_process_action(void) {}

int main(void)
{
  sl_system_init();
  app_init();

#if defined(SL_CATALOG_KERNEL_PRESENT)
  sl_system_kernel_start();
#else
  while (1) {
    sl_system_process_action();
    app_process_action();

#if defined(SL_CATALOG_POWER_MANAGER_PRESENT)
    // *** SLEEP ENABLED FOR SLEEPY END DEVICE ***
    // Device will enter EM2/EM3 when idle, wake on:
    //   - sl_zigbee_event timer expiry
    //   - Poll timer (LONG_POLL or SHORT_POLL)
    //   - UART RX (for CLI, if configured)
    // Radio is automatically turned OFF during sleep.
    sl_power_manager_sleep();
#endif
  }
#endif
  return 0;
}
