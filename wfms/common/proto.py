"""
UART Protocol Parser/Builder for Zigbee Coordinator

Coordinator Protocol (from coordinator_protocol_spec.md):
- Baud: 115200, 8N1, LF line ending
- @INFO {"node_id":"0x0000","eui64":"...","pan_id":"0xBEEF",...}
- @DATA {"flow":150,"valve":"open","battery":85,"mode":"auto",...}
- @ACK {"id":123,"ok":true,"msg":"..."}
- @LOG {"tag":"NET","event":"formed",...}
- @CMD {"id":<uint32>,"op":"<operation>",...params}

Available Operations:
- info, mode_set, threshold_set, valve_set, valve_path_set,
- valve_target_set, valve_pair, net_cfg_set, net_form, uart_gateway_set

DO NOT BREAK: Parse functions must handle all documented formats.
"""

import json
import time
import hashlib
from typing import Tuple, Dict, Any, Optional, List
from enum import Enum


# Protocol prefixes (UART)
PREFIX_DATA = "@DATA"
PREFIX_ACK = "@ACK"
PREFIX_CMD = "@CMD"
PREFIX_LOG = "@LOG"
PREFIX_INFO = "@INFO"

# CID to numeric ID tracking (for ACK matching)
_cid_to_id: Dict[str, int] = {}
_id_counter: int = 1


class Operation(str, Enum):
    """Available Coordinator operations."""
    INFO = "info"
    MODE_SET = "mode_set"
    THRESHOLD_SET = "threshold_set"
    VALVE_SET = "valve_set"
    VALVE_PATH_SET = "valve_path_set"
    VALVE_TARGET_SET = "valve_target_set"
    VALVE_PAIR = "valve_pair"
    NET_CFG_SET = "net_cfg_set"
    NET_FORM = "net_form"
    UART_GATEWAY_SET = "uart_gateway_set"


# Valve state mapping: MQTT (ON/OFF) <-> Coordinator (open/closed)
VALVE_MQTT_TO_COORD = {"ON": "open", "OFF": "closed"}
VALVE_COORD_TO_MQTT = {"open": "ON", "closed": "OFF", "close": "OFF"}

# Mode values
MODE_AUTO = "auto"
MODE_MANUAL = "manual"

# Valve path values
VALVE_PATH_AUTO = "auto"
VALVE_PATH_DIRECT = "direct"
VALVE_PATH_BINDING = "binding"


def parse_uart_line(line: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse a UART line into (type, payload_dict).
    
    Args:
        line: Raw line from UART (may include newline)
    
    Returns:
        Tuple of (type, payload):
        - type: "DATA", "ACK", "CMD", "LOG", "INFO", or "ERR"
        - payload: Parsed JSON dict, or {"error": "message", "raw": line} on error
    
    Examples:
        >>> parse_uart_line('@DATA {"flow":150,"valve":"open","battery":85}')
        ("DATA", {"flow": 150, "valve": "open", "battery": 85})
        
        >>> parse_uart_line('@ACK {"id":1,"ok":true,"msg":"valve set"}')
        ("ACK", {"id": 1, "ok": True, "msg": "valve set"})
        
        >>> parse_uart_line('@INFO {"node_id":"0x0000","pan_id":"0xBEEF","ch":11}')
        ("INFO", {"node_id": "0x0000", "pan_id": "0xBEEF", "ch": 11})
    """
    line = line.strip()
    
    if not line:
        return ("ERR", {"error": "empty_line", "raw": ""})
    
    # Determine prefix and extract JSON part
    prefix_map = {
        PREFIX_DATA: "DATA",
        PREFIX_ACK: "ACK",
        PREFIX_CMD: "CMD",
        PREFIX_LOG: "LOG",
        PREFIX_INFO: "INFO",
    }
    
    msg_type = None
    json_part = None
    
    for prefix, type_name in prefix_map.items():
        if line.startswith(prefix):
            msg_type = type_name
            json_part = line[len(prefix):].strip()
            break
    
    if msg_type is None:
        return ("ERR", {"error": "unknown_prefix", "raw": line})
    
    if not json_part:
        return ("ERR", {"error": "missing_payload", "raw": line})
    
    try:
        payload = json.loads(json_part)
        if not isinstance(payload, dict):
            return ("ERR", {"error": "payload_not_dict", "raw": line})
        return (msg_type, payload)
    except json.JSONDecodeError as e:
        return ("ERR", {"error": f"json_parse_error: {e}", "raw": line})


def _cid_to_numeric_id(cid: str) -> int:
    """Convert string CID to numeric ID for Coordinator."""
    global _id_counter
    if cid not in _cid_to_id:
        _cid_to_id[cid] = _id_counter
        _id_counter += 1
    return _cid_to_id[cid]


def _numeric_id_to_cid(numeric_id: int) -> Optional[str]:
    """Convert numeric ID back to CID (for ACK matching)."""
    for cid, id_val in _cid_to_id.items():
        if id_val == numeric_id:
            return cid
    return None


def make_cmd_line(cmd_dict: Dict[str, Any], operation: Optional[str] = None) -> str:
    """
    Create a @CMD line to send via UART.
    
    Supports two modes:
    1. MQTT valve command format (legacy):
       Input:  {"cid":"xxx","value":"ON","by":"user","ts":123}
       Output: @CMD {"id":N,"op":"valve_set","value":"open"}
    
    2. Direct Coordinator format (new):
       Input:  {"op":"mode_set","value":"manual"}
       Output: @CMD {"id":N,"op":"mode_set","value":"manual"}
    
    Args:
        cmd_dict: Command payload dict
        operation: Override operation type (optional)
    
    Returns:
        Formatted line: "@CMD {...}\\n"
    
    Examples:
        >>> make_cmd_line({"cid": "abc", "value": "ON"})
        '@CMD {"id":1,"op":"valve_set","value":"open"}\\n'
        
        >>> make_cmd_line({"op": "mode_set", "value": "manual"})
        '@CMD {"id":2,"op":"mode_set","value":"manual"}\\n'
        
        >>> make_cmd_line({"op": "info"})
        '@CMD {"id":3,"op":"info"}\\n'
    """
    # Determine if this is MQTT format or Coordinator format
    if "op" in cmd_dict:
        # Coordinator format - use directly with ID assigned
        op = operation or cmd_dict.get("op")
        cid = cmd_dict.get("cid", f"auto_{_id_counter}")
        numeric_id = _cid_to_numeric_id(cid)
        
        # Build command with required fields
        coord_cmd = {"id": numeric_id, "op": op}
        
        # Copy optional parameters based on operation
        optional_fields = ["value", "close_th", "open_th", "node_id", "dst_ep", 
                          "eui64", "bind_index", "pan_id", "ch", "tx_power", 
                          "force", "enable"]
        for field in optional_fields:
            if field in cmd_dict:
                coord_cmd[field] = cmd_dict[field]
        
        json_str = json.dumps(coord_cmd, separators=(',', ':'))
        return f"{PREFIX_CMD} {json_str}\n"
    
    # MQTT valve command format (legacy)
    cid = cmd_dict.get("cid", "unknown")
    mqtt_value = cmd_dict.get("value", "").upper()
    
    # Map MQTT value (ON/OFF) to Coordinator value (open/closed)
    coord_value = VALVE_MQTT_TO_COORD.get(mqtt_value, mqtt_value.lower())
    
    # Convert CID to numeric ID (Coordinator expects number)
    numeric_id = _cid_to_numeric_id(cid)
    
    # Build Coordinator format
    coord_cmd = {
        "id": numeric_id,
        "op": operation or Operation.VALVE_SET.value,
        "value": coord_value
    }
    
    json_str = json.dumps(coord_cmd, separators=(',', ':'))
    return f"{PREFIX_CMD} {json_str}\n"


# ============================================================================
# Coordinator Command Builders
# ============================================================================

def make_info_cmd(cid: Optional[str] = None) -> str:
    """Create info command to get system status."""
    return make_cmd_line({"cid": cid or f"info_{_id_counter}", "op": Operation.INFO.value})


def make_mode_set_cmd(mode: str, cid: Optional[str] = None) -> str:
    """
    Create mode_set command.
    
    Args:
        mode: "auto" or "manual"
        cid: Optional correlation ID
    """
    if mode not in (MODE_AUTO, MODE_MANUAL):
        raise ValueError(f"Invalid mode: {mode}. Must be 'auto' or 'manual'")
    return make_cmd_line({
        "cid": cid or f"mode_{_id_counter}",
        "op": Operation.MODE_SET.value,
        "value": mode
    })


def make_threshold_set_cmd(close_th: int, open_th: int = 0, cid: Optional[str] = None) -> str:
    """
    Create threshold_set command.
    
    Args:
        close_th: Threshold to close valve (required)
        open_th: Threshold to open valve (must be < close_th)
        cid: Optional correlation ID
    """
    if open_th >= close_th:
        raise ValueError(f"open_th ({open_th}) must be < close_th ({close_th})")
    return make_cmd_line({
        "cid": cid or f"threshold_{_id_counter}",
        "op": Operation.THRESHOLD_SET.value,
        "close_th": close_th,
        "open_th": open_th
    })


def make_valve_set_cmd(state: str, cid: Optional[str] = None) -> str:
    """
    Create valve_set command.
    
    Args:
        state: "open" or "closed" (Coordinator format) or "ON"/"OFF" (MQTT format)
        cid: Optional correlation ID
    """
    # Normalize to Coordinator format
    if state.upper() in VALVE_MQTT_TO_COORD:
        state = VALVE_MQTT_TO_COORD[state.upper()]
    elif state.lower() not in ("open", "closed", "close"):
        raise ValueError(f"Invalid valve state: {state}")
    else:
        state = state.lower()
    
    return make_cmd_line({
        "cid": cid or f"valve_{_id_counter}",
        "op": Operation.VALVE_SET.value,
        "value": state
    })


def make_valve_path_cmd(path: str, cid: Optional[str] = None) -> str:
    """
    Create valve_path_set command.
    
    Args:
        path: "auto", "direct", or "binding"
        cid: Optional correlation ID
    """
    if path not in (VALVE_PATH_AUTO, VALVE_PATH_DIRECT, VALVE_PATH_BINDING):
        raise ValueError(f"Invalid path: {path}")
    return make_cmd_line({
        "cid": cid or f"path_{_id_counter}",
        "op": Operation.VALVE_PATH_SET.value,
        "value": path
    })


def make_valve_target_cmd(node_id: int, dst_ep: int = 1, cid: Optional[str] = None) -> str:
    """
    Create valve_target_set command.
    
    Args:
        node_id: Short address (decimal)
        dst_ep: Destination endpoint (default: 1)
        cid: Optional correlation ID
    """
    return make_cmd_line({
        "cid": cid or f"target_{_id_counter}",
        "op": Operation.VALVE_TARGET_SET.value,
        "node_id": node_id,
        "dst_ep": dst_ep
    })


def make_valve_pair_cmd(
    eui64: str, 
    node_id: int, 
    bind_index: int = 0, 
    dst_ep: int = 1, 
    cid: Optional[str] = None
) -> str:
    """
    Create valve_pair command.
    
    Args:
        eui64: 16 hex chars (big-endian)
        node_id: Short address
        bind_index: Index in binding table
        dst_ep: Destination endpoint
        cid: Optional correlation ID
    """
    if len(eui64) != 16 or not all(c in '0123456789ABCDEFabcdef' for c in eui64):
        raise ValueError(f"Invalid EUI64: {eui64}. Must be 16 hex chars.")
    return make_cmd_line({
        "cid": cid or f"pair_{_id_counter}",
        "op": Operation.VALVE_PAIR.value,
        "eui64": eui64.upper(),
        "node_id": node_id,
        "bind_index": bind_index,
        "dst_ep": dst_ep
    })


def make_net_form_cmd(
    pan_id: Optional[int] = None,
    ch: Optional[int] = None,
    tx_power: Optional[int] = None,
    force: bool = False,
    cid: Optional[str] = None
) -> str:
    """
    Create net_form command.
    
    Args:
        pan_id: PAN ID (0x0000-0xFFFE), uses current if not provided
        ch: Channel (11-26), uses current if not provided
        tx_power: TX power in dBm, uses current if not provided
        force: If True, leave network before forming new
        cid: Optional correlation ID
    """
    cmd = {
        "cid": cid or f"form_{_id_counter}",
        "op": Operation.NET_FORM.value
    }
    if pan_id is not None:
        if not (0x0000 <= pan_id <= 0xFFFE):
            raise ValueError(f"Invalid PAN ID: {pan_id}")
        cmd["pan_id"] = pan_id
    if ch is not None:
        if not (11 <= ch <= 26):
            raise ValueError(f"Invalid channel: {ch}. Must be 11-26.")
        cmd["ch"] = ch
    if tx_power is not None:
        cmd["tx_power"] = tx_power
    if force:
        cmd["force"] = 1
    return make_cmd_line(cmd)


def make_uart_gateway_cmd(enable: bool, cid: Optional[str] = None) -> str:
    """
    Create uart_gateway_set command.
    
    Args:
        enable: True to enable, False to disable
        cid: Optional correlation ID
    """
    return make_cmd_line({
        "cid": cid or f"uart_{_id_counter}",
        "op": Operation.UART_GATEWAY_SET.value,
        "enable": 1 if enable else 0
    })


def make_data_line(data_dict: Dict[str, Any]) -> str:
    """
    Create a @DATA line (used by FakeUart).
    
    Args:
        data_dict: Data payload dict with keys: flow, battery, valve, mode, etc.
    
    Returns:
        Formatted line: "@DATA {...}\n"
    """
    json_str = json.dumps(data_dict, separators=(',', ':'))
    return f"{PREFIX_DATA} {json_str}\n"


def make_ack_line(ack_dict: Dict[str, Any]) -> str:
    """
    Create an @ACK line (used by FakeUart).
    
    Coordinator format: {"id":N,"ok":true,"msg":"..."}
    
    Args:
        ack_dict: ACK payload dict with keys: id, ok, msg
    
    Returns:
        Formatted line: "@ACK {...}\n"
    """
    json_str = json.dumps(ack_dict, separators=(',', ':'))
    return f"{PREFIX_ACK} {json_str}\n"


def make_info_line(info_dict: Dict[str, Any]) -> str:
    """
    Create an @INFO line (used by FakeUart for heartbeat).
    
    Args:
        info_dict: INFO payload with node_id, pan_id, ch, etc.
    
    Returns:
        Formatted line: "@INFO {...}\n"
    """
    json_str = json.dumps(info_dict, separators=(',', ':'))
    return f"{PREFIX_INFO} {json_str}\n"


def make_log_line(tag: str, event: str, **extra) -> str:
    """
    Create a @LOG line.
    
    Args:
        tag: Log tag (e.g., "NET", "CMD", "ERR")
        event: Event description
        **extra: Additional fields
    
    Returns:
        Formatted line: "@LOG {...}\n"
    """
    log_dict = {"tag": tag, "event": event, **extra}
    json_str = json.dumps(log_dict, separators=(',', ':'))
    return f"{PREFIX_LOG} {json_str}\n"


def translate_coordinator_ack(coord_ack: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate Coordinator ACK format to MQTT contract format.
    
    Coordinator: {"id":123,"ok":true,"msg":"...","valve":"open","mode":"auto"}
    MQTT:        {"cid":"xxx","ok":true,"reason":"..."}
    
    Args:
        coord_ack: ACK payload from Coordinator
    
    Returns:
        Translated ACK for MQTT with original fields preserved
    """
    numeric_id = coord_ack.get("id", 0)
    ok = coord_ack.get("ok", False)
    msg = coord_ack.get("msg", "")
    
    # Try to find original CID from numeric ID
    cid = _numeric_id_to_cid(numeric_id)
    if cid is None:
        cid = f"id_{numeric_id}"  # Fallback if CID not found
    
    mqtt_ack = {
        "cid": cid,
        "ok": ok,
        "reason": msg
    }
    
    # Preserve additional fields from Coordinator ACK (valve, mode, etc.)
    for key in ["valve", "mode", "valve_path", "valve_known", "valve_node_id"]:
        if key in coord_ack:
            mqtt_ack[key] = coord_ack[key]
    
    return mqtt_ack


def translate_coordinator_data(coord_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate Coordinator DATA format to MQTT format.
    
    Coordinator: {"flow":150,"valve":"open","battery":85,"mode":"auto",...}
    MQTT:        {"flow":150,"valve":"ON","battery":85,"mode":"auto",...}
    
    Args:
        coord_data: DATA payload from Coordinator
    
    Returns:
        Translated DATA for MQTT/State
    """
    mqtt_data = coord_data.copy()
    
    # Translate valve state (open/closed -> ON/OFF)
    if "valve" in mqtt_data:
        valve_state = mqtt_data["valve"].lower()
        mqtt_data["valve"] = VALVE_COORD_TO_MQTT.get(valve_state, "OFF")
    
    return mqtt_data


def now_ts() -> int:
    """Return current Unix timestamp (seconds)."""
    return int(time.time())


def validate_cmd_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate a command payload from MQTT.
    
    Args:
        payload: Command dict to validate
    
    Returns:
        Tuple of (is_valid, error_reason)
    """
    if not isinstance(payload, dict):
        return (False, "payload_not_dict")
    
    cid = payload.get("cid")
    if not cid or not isinstance(cid, str):
        return (False, "missing_cid")
    
    value = payload.get("value")
    if value not in ("ON", "OFF"):
        return (False, "invalid_value")
    
    # "by" and "ts" are optional but recommended
    return (True, "")


# ============================================================================
# Coordinator Error Messages (for reference)
# ============================================================================

COORDINATOR_ERRORS = {
    "missing op": "Missing 'op' field in command",
    "missing value": "Missing 'value' field for operation that requires it",
    "debounced": "Command sent too quickly (<500ms debounce)",
    "rejected: AUTO mode": "valve_set rejected - Coordinator is in AUTO mode",
    "unknown op": "Unknown operation name",
    "bad channel": "Channel not in valid range (11-26)",
    "open_th must be < close_th": "Invalid threshold values",
}


# ============================================================================
# Protocol Constants
# ============================================================================

# Timing constants (from Coordinator)
DEBOUNCE_MS = 500  # Min time between mode_set/valve_set commands
DUPLICATE_WINDOW_MS = 2000  # Window to ignore duplicate command IDs
DEFAULT_NETWORK_JOIN_WINDOW_S = 180  # Seconds network accepts joins after form

# Valid channels
VALID_CHANNELS = range(11, 27)  # 11-26

# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Parsing
    "parse_uart_line",
    
    # Line builders
    "make_cmd_line",
    "make_data_line",
    "make_ack_line",
    "make_info_line",
    "make_log_line",
    
    # Command builders
    "make_info_cmd",
    "make_mode_set_cmd",
    "make_threshold_set_cmd",
    "make_valve_set_cmd",
    "make_valve_path_cmd",
    "make_valve_target_cmd",
    "make_valve_pair_cmd",
    "make_net_form_cmd",
    "make_uart_gateway_cmd",
    
    # Translation
    "translate_coordinator_ack",
    "translate_coordinator_data",
    
    # Utilities
    "now_ts",
    "validate_cmd_payload",
    
    # Constants
    "PREFIX_DATA",
    "PREFIX_ACK",
    "PREFIX_CMD",
    "PREFIX_LOG",
    "PREFIX_INFO",
    "Operation",
    "VALVE_MQTT_TO_COORD",
    "VALVE_COORD_TO_MQTT",
    "MODE_AUTO",
    "MODE_MANUAL",
    "DEBOUNCE_MS",
    "VALID_CHANNELS",
]
