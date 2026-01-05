#ifndef APP_LOG_H
#define APP_LOG_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void printInfoToPC(void);

// Các hàm bạn đang gọi trong app.c/buttons.c/cmd_handler.c
void appLogInfo(void);
void appLogData(void);
void appLogLog(const char *tag, const char *event, const char *value);
void appLogAck(uint32_t id, bool ok, const char *msg);

#ifdef __cplusplus
}
#endif

#endif // APP_LOG_H
