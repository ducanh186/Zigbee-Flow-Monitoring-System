"""
Gateway Runtime State

Shared state between GatewayService and Admin API.
Thread-safe implementation for concurrent access.
"""

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class LogEntry:
    """Single log entry for the Admin API."""
    ts: float
    level: str
    message: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {"ts": self.ts, "level": self.level, "message": self.message}


class RuntimeState:
    """
    Shared runtime state for the gateway service.
    
    Thread-safe access to:
    - Health status
    - Recent logs buffer
    - Service metrics
    """
    
    def __init__(self, max_logs: int = 100):
        self._lock = threading.Lock()
        
        # Health tracking
        self._started_at: float = time.time()
        self._mqtt_connected: bool = False
        self._uart_connected: bool = False
        
        # Logs buffer (ring buffer)
        self._logs: deque = deque(maxlen=max_logs)
        
        # Counters
        self._telemetry_count: int = 0
        self._cmd_count: int = 0
        self._ack_ok_count: int = 0
        self._ack_fail_count: int = 0
    
    # -------------------- Health --------------------
    
    def set_mqtt_connected(self, connected: bool) -> None:
        """Update MQTT connection status."""
        with self._lock:
            self._mqtt_connected = connected
    
    def set_uart_connected(self, connected: bool) -> None:
        """Update UART connection status."""
        with self._lock:
            self._uart_connected = connected
    
    def get_health(self) -> Dict[str, Any]:
        """Get health status for Admin API."""
        with self._lock:
            uptime_s = time.time() - self._started_at
            return {
                "up": self._mqtt_connected,
                "uptime_s": round(uptime_s, 1),
                "mqtt_connected": self._mqtt_connected,
                "uart_connected": self._uart_connected,
                "counters": {
                    "telemetry": self._telemetry_count,
                    "commands": self._cmd_count,
                    "ack_ok": self._ack_ok_count,
                    "ack_fail": self._ack_fail_count,
                }
            }
    
    # -------------------- Counters --------------------
    
    def inc_telemetry(self) -> None:
        """Increment telemetry counter."""
        with self._lock:
            self._telemetry_count += 1
    
    def inc_cmd(self) -> None:
        """Increment command counter."""
        with self._lock:
            self._cmd_count += 1
    
    def inc_ack(self, ok: bool) -> None:
        """Increment ACK counter (ok or fail)."""
        with self._lock:
            if ok:
                self._ack_ok_count += 1
            else:
                self._ack_fail_count += 1
    
    # -------------------- Logs --------------------
    
    def add_log(self, level: str, message: str) -> None:
        """Add a log entry to the buffer."""
        entry = LogEntry(ts=time.time(), level=level, message=message)
        with self._lock:
            self._logs.append(entry)
    
    def get_logs(self, limit: int = 50, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get recent logs.
        
        Args:
            limit: Maximum number of logs to return
            level: Filter by level (DEBUG, INFO, WARNING, ERROR)
        
        Returns:
            List of log entries (newest first)
        """
        with self._lock:
            logs = list(self._logs)
        
        # Filter by level if specified
        if level:
            level_upper = level.upper()
            logs = [log for log in logs if log.level == level_upper]
        
        # Return newest first, limited
        return [log.to_dict() for log in reversed(logs)][:limit]


class RuntimeLogHandler:
    """
    Custom log handler that captures logs to RuntimeState.
    
    Usage:
        runtime = RuntimeState()
        handler = RuntimeLogHandler(runtime)
        logger.addHandler(handler)
    """
    
    def __init__(self, runtime: RuntimeState, capture_levels: tuple = ("INFO", "WARNING", "ERROR", "CRITICAL")):
        self.runtime = runtime
        self.capture_levels = capture_levels
    
    def handle(self, level: str, message: str) -> None:
        """Handle a log message."""
        if level in self.capture_levels:
            self.runtime.add_log(level, message)
