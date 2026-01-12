#include "sl_system_init.h"
#include "sl_system_process_action.h"
#include "sl_event_handler.h"       // For sl_platform_process_action, sl_stack_process_action, etc.
#include "sl_cli_instances.h"       // For sl_cli_instances_tick
#include "app/app_state.h"          // For g_uartGatewayEnabled

int main(void)
{
  sl_system_init();

  while (1) {
    // =========================================================================
    // FIX 1: Avoid race condition - only ONE owner reads UART RX at a time
    // =========================================================================
    // Instead of calling sl_system_process_action() which always calls
    // sl_cli_instances_tick(), we manually call the sub-functions and
    // conditionally skip CLI tick when Gateway mode is ON.
    // =========================================================================

    sl_platform_process_action();    // Platform tasks (always run)

    // FIX 1: CLI vs Gateway mode mutual exclusion
    // - IDE Mode (gateway OFF): CLI owns UART RX -> call sl_cli_instances_tick()
    // - Dashboard Mode (gateway ON): uartLinkPoll() owns RX -> skip CLI tick
    if (!g_uartGatewayEnabled) {
      sl_service_process_action();   // Contains sl_cli_instances_tick()
    }
    // Note: uartLinkPoll() is called in emberAfMainTickCallback() when
    //       g_uartGatewayEnabled == true (see app/app.c)

    sl_stack_process_action();       // Zigbee stack + App Framework tick
    sl_internal_app_process_action(); // Internal app tasks
  }
}
