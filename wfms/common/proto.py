"""
UART Protocol Parser/Builder

Protocol format:
- @DATA {"flow":12.5,"battery":85,"valve":"ON","ts":1234567890}
- @ACK {"cid":"xxx","ok":true,"reason":"","ts":1234567890}
- @CMD {"cid":"xxx","value":"ON","by":"user","ts":1234567890}
- @LOG {...} (optional, for debugging)

DO NOT BREAK: Parse functions must handle all documented formats.
"""

import json
import time
import hashlib
from typing import Tuple, Dict, Any, Optional


# Protocol prefixes (UART)
PREFIX_DATA = "@DATA"
PREFIX_ACK = "@ACK"
PREFIX_CMD = "@CMD"
PREFIX_LOG = "@LOG"
PREFIX_INFO = "@INFO"

# CID to numeric ID tracking (for ACK matching)
_cid_to_id: Dict[str, int] = {}
_id_counter: int = 1


def parse_uart_line(line: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse a UART line into (type, payload_dict).
    
    Args:
        line: Raw line from UART (may include newline)
    
    Returns:
        Tuple of (type, payload):
        - type: "DATA", "ACK", "CMD", "LOG", or "ERR"
        - payload: Parsed JSON dict, or {"error": "message", "raw": line} on error
    
    Examples:
        >>> parse_uart_line('@DATA {"flow":12.5,"battery":85}')
        ("DATA", {"flow": 12.5, "battery": 85})
        
        >>> parse_uart_line('@ACK {"cid":"abc","ok":true}')
        ("ACK", {"cid": "abc", "ok": True})
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


def make_cmd_line(cmd_dict: Dict[str, Any]) -> str:
    """
    Create a @CMD line to send via UART.
    
    Translates MQTT contract format to Coordinator format:
    - MQTT: {"cid":"xxx","value":"ON","by":"user","ts":123}
    - UART: {"id":123,"op":"valve_set","value":"open"}
    
    Args:
        cmd_dict: Command payload dict with keys: cid, value, by, ts
    
    Returns:
        Formatted line: "@CMD {...}\\n"
    
    Example:
        >>> make_cmd_line({"cid": "abc", "value": "ON", "by": "admin", "ts": 123})
        '@CMD {"id":1,"op":"valve_set","value":"open"}\\n'
    """
    cid = cmd_dict.get("cid", "unknown")
    mqtt_value = cmd_dict.get("value", "").upper()
    
    # Map MQTT value (ON/OFF) to Coordinator value (open/closed)
    if mqtt_value == "ON":
        coord_value = "open"
    elif mqtt_value == "OFF":
        coord_value = "closed"
    else:
        coord_value = mqtt_value.lower()  # Pass through other values
    
    # Convert CID to numeric ID (Coordinator expects number)
    numeric_id = _cid_to_numeric_id(cid)
    
    # Build Coordinator format
    coord_cmd = {
        "id": numeric_id,
        "op": "valve_set",
        "value": coord_value
    }
    
    json_str = json.dumps(coord_cmd, separators=(',', ':'))
    return f"{PREFIX_CMD} {json_str}\n"


def make_data_line(data_dict: Dict[str, Any]) -> str:
    """
    Create a @DATA line (used by FakeUart).
    
    Args:
        data_dict: Data payload dict with keys: flow, battery, valve, ts
    
    Returns:
        Formatted line: "@DATA {...}\n"
    """
    json_str = json.dumps(data_dict, separators=(',', ':'))
    return f"{PREFIX_DATA} {json_str}\n"


def make_ack_line(ack_dict: Dict[str, Any]) -> str:
    """
    Create an @ACK line (used by FakeUart).
    
    Args:
        ack_dict: ACK payload dict with keys: cid, ok, reason, ts
    
    Returns:
        Formatted line: "@ACK {...}\n"
    """
    json_str = json.dumps(ack_dict, separators=(',', ':'))
    return f"{PREFIX_ACK} {json_str}\n"


def translate_coordinator_ack(coord_ack: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate Coordinator ACK format to MQTT contract format.
    
    Coordinator: {"id":123,"ok":true,"msg":"...","valve":"open"}
    MQTT:        {"cid":"xxx","ok":true,"reason":"..."}
    
    Args:
        coord_ack: ACK payload from Coordinator
    
    Returns:
        Translated ACK for MQTT
    """
    numeric_id = coord_ack.get("id", 0)
    ok = coord_ack.get("ok", False)
    msg = coord_ack.get("msg", "")
    
    # Try to find original CID from numeric ID
    cid = _numeric_id_to_cid(numeric_id)
    if cid is None:
        cid = f"id_{numeric_id}"  # Fallback if CID not found
    
    return {
        "cid": cid,
        "ok": ok,
        "reason": msg
    }


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
