#include "uart_link.h"
#include "app_config.h"
#include "cmd_handler.h"

#include "sl_iostream.h"
#include "sl_status.h"

#include <stddef.h>
#include <string.h>
#include <stdint.h>

static char s_uartLine[UART_LINE_MAX];
static uint16_t s_uartLen = 0;

void uartLinkPoll(void)
{
  char c;
  size_t n = 0;
  sl_status_t st = sl_iostream_read(SL_IOSTREAM_STDIN, &c, 1, &n);

  while ((st == SL_STATUS_OK) && (n == 1)) {

    if (c == '\r') {
      // ignore
    } else if (c == '\n') {
      if (s_uartLen > 0) {
        s_uartLine[s_uartLen] = 0;
        if (strncmp(s_uartLine, "@CMD", 4) == 0) {
          cmdHandleLine(s_uartLine);
        }
        s_uartLen = 0;
      }
    } else {
      if ((uint16_t)(s_uartLen + 1u) < (uint16_t)UART_LINE_MAX) {
        s_uartLine[s_uartLen++] = c;
      } else {
        // overflow -> drop line
        s_uartLen = 0;
      }
    }

    n = 0;
    st = sl_iostream_read(SL_IOSTREAM_STDIN, &c, 1, &n);
  }
}
