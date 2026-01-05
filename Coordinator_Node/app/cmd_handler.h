#ifndef CMD_HANDLER_H
#define CMD_HANDLER_H

#include "sl_cli.h"

// Called from uartLinkPoll() when @CMD line is parsed
void cmdHandleLine(const char *line);

// CLI command handler for "json {...}" - called by CLI framework
void cli_json_command(sl_cli_command_arg_t *arguments);

#endif
