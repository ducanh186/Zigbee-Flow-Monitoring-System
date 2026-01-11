#ifndef APP_LOG_H
#define APP_LOG_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ===== STABLE UART LINE PROTOCOL =====
// All output follows: "@PREFIX <compact JSON>\r\n"
// Prefixes: @INFO, @DATA, @LOG, @ACK

// === INFO: System/network status (periodic heartbeat + on-demand) ===
void appLogInfo(void);

// === DATA: Telemetry (periodic + on-change) ===
void appLogData(void);

// === LOG: Events and debug (structured logging) ===
// tag: short category (NET, ZB, CMD, SYS)
// event: what happened (join, send, error, etc.)
// Extra key-value pairs via format string
void appLogLog(const char *tag, const char *event, const char *fmt, ...);

// === ACK: Command acknowledgment (ALWAYS sent for every @CMD) ===
// id: command ID from @CMD (use -1 if parse failed)
// ok: true if command succeeded, false otherwise
// msg: short status message
void appLogAck(uint32_t id, bool ok, const char *msg);

// Extended ACK with Zigbee status
void appLogAckZb(uint32_t id, bool ok, const char *msg, uint8_t zstatus, const char *stage);

// === HEARTBEAT: Periodic @INFO emission ===
#define HEARTBEAT_INTERVAL_MS  30000u   // 30 seconds
void appLogHeartbeatTick(void);         // Call from main tick
void appLogEmitHeartbeat(void);         // Force emit @INFO now

// === UPTIME tracking ===
uint32_t appLogGetUptimeSec(void);

// === LEGACY (deprecated, use appLogInfo) ===
void printInfoToPC(void);

#ifdef __cplusplus
}
#endif

#endif // APP_LOG_H
