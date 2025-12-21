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

#include "sl_simple_led_instances.h"

void app_init(void)
{
  sl_led_turn_off(&sl_led_led0); // default close
}

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
    sl_power_manager_sleep();
#endif
  }
#endif
  return 0;
}
