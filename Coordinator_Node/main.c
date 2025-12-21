#include "sl_system_init.h"
#include "sl_system_process_action.h"

int main(void)
{
  sl_system_init();

  while (1) {
    sl_system_process_action();
  }
}
