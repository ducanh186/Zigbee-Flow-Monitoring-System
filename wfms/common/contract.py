"""
WFMS Contract Constants
DO NOT BREAK: Chỉ được thêm constants mới, không đổi/xóa constants cũ.
"""

# Site identifier (default, can be overridden by .env)
SITE = "lab1"

# MQTT topic base
TOPIC_BASE = f"wfms/{SITE}"

# MQTT Topics
TOPIC_STATE = f"{TOPIC_BASE}/state"              # Gateway publishes state (retained)
TOPIC_TELEMETRY = f"{TOPIC_BASE}/telemetry"      # Gateway publishes telemetry
TOPIC_CMD_VALVE = f"{TOPIC_BASE}/cmd/valve"      # Dashboard publishes valve commands
TOPIC_CMD_MODE = f"{TOPIC_BASE}/cmd/mode"        # Dashboard publishes mode commands (auto/manual)
TOPIC_ACK = f"{TOPIC_BASE}/ack"                  # Gateway publishes acknowledgments
TOPIC_GATEWAY_STATUS = f"{TOPIC_BASE}/status/gateway"  # Gateway heartbeat/LWT (retained)

# Valve states
VALVE_ON = "ON"
VALVE_OFF = "OFF"

# Gateway status
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"

# UART Protocol markers (for future use)
UART_DATA_PREFIX = "@DATA"
UART_ACK_PREFIX = "@ACK"
UART_CMD_PREFIX = "@CMD"


def update_site(site: str) -> None:
    """
    Update SITE and regenerate all topic constants.
    Call this after loading config.
    """
    global SITE, TOPIC_BASE, TOPIC_STATE, TOPIC_TELEMETRY, TOPIC_CMD_VALVE, TOPIC_CMD_MODE, TOPIC_ACK, TOPIC_GATEWAY_STATUS
    
    SITE = site
    TOPIC_BASE = f"wfms/{SITE}"
    TOPIC_STATE = f"{TOPIC_BASE}/state"
    TOPIC_TELEMETRY = f"{TOPIC_BASE}/telemetry"
    TOPIC_CMD_VALVE = f"{TOPIC_BASE}/cmd/valve"
    TOPIC_CMD_MODE = f"{TOPIC_BASE}/cmd/mode"
    TOPIC_ACK = f"{TOPIC_BASE}/ack"
    TOPIC_GATEWAY_STATUS = f"{TOPIC_BASE}/status/gateway"
