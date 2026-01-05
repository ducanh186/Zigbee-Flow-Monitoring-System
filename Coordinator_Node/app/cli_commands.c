/**
 * @file cli_commands.c
 * @brief Custom CLI command for Dashboard JSON protocol
 * 
 * IDE Mode: Use built-in SDK CLI commands (info, network form, plugin commands, etc.)
 * Dashboard Mode: Use "json" command to process JSON from Dashboard
 * 
 * Toggle between modes: Long press PB0
 */

#include "sl_cli.h"
#include "sl_cli_instances.h"
#include "sl_cli_command.h"
#include "sl_cli_handles.h"
#include "cmd_handler.h"
#include "app/framework/include/af.h"

#include <string.h>
#include <stdio.h>

// ========== CLI COMMAND HANDLER ==========

// "json" command: json {"id":1,"op":"info"}
// Used by Dashboard to send commands
void cli_cmd_json(sl_cli_command_arg_t *arguments)
{
  char *json_arg = sl_cli_get_argument_string(arguments, 0);
  if (!json_arg || json_arg[0] == '\0') {
    emberAfCorePrintln("Usage: json {\"id\":N,\"op\":\"...\"}");
    return;
  }
  
  // Build @CMD line and process
  static char cmdBuf[256];
  int n = snprintf(cmdBuf, sizeof(cmdBuf), "@CMD %s", json_arg);
  if (n < 0 || (size_t)n >= sizeof(cmdBuf)) {
    emberAfCorePrintln("json: command too long");
    return;
  }
  
  cmdHandleLine(cmdBuf);
}

// ========== COMMAND TABLE ==========

static const sl_cli_command_info_t cli_cmd_json_info = 
  SL_CLI_COMMAND(cli_cmd_json,
                 "Process JSON command (Dashboard mode)",
                 "JSON payload" SL_CLI_UNIT_SEPARATOR,
                 { SL_CLI_ARG_STRING, SL_CLI_ARG_END });

static const sl_cli_command_entry_t custom_cmd_table[] = {
  { "json", &cli_cmd_json_info, false },
  { NULL, NULL, false }
};

static sl_cli_command_group_t custom_cmd_group = {
  { NULL },
  false,
  custom_cmd_table
};

// ========== INITIALIZATION ==========

void customCliInit(void)
{
  // Register only "json" command for Dashboard mode
  sl_cli_command_add_command_group(sl_cli_example_handle, &custom_cmd_group);
  emberAfCorePrintln("Dashboard command registered: json");
}
