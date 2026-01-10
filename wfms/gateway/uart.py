"""
UART Interface - Real and Fake implementations

Provides:
- UartBase: Abstract interface
- RealUart: pyserial-based real UART connection with auto-reconnect
- FakeUart: Simulated UART for UI development without hardware
"""

import threading
import queue
import time
import random
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable

from common.proto import (
    make_data_line, make_ack_line, make_info_line, parse_uart_line, now_ts,
    VALVE_MQTT_TO_COORD, VALVE_COORD_TO_MQTT, MODE_AUTO, MODE_MANUAL
)

logger = logging.getLogger(__name__)


class UartBase(ABC):
    """Abstract UART interface."""
    
    @abstractmethod
    def start(self) -> None:
        """Start the UART connection/emulation."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop and cleanup."""
        pass
    
    @abstractmethod
    def read_line(self, timeout: float = 1.0) -> Optional[str]:
        """
        Read a line from UART.
        
        Args:
            timeout: Max seconds to wait
        
        Returns:
            Line string (with newline stripped) or None on timeout
        """
        pass
    
    @abstractmethod
    def write_line(self, line: str) -> bool:
        """
        Write a line to UART.
        
        Args:
            line: Line to write (should include newline)
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if UART is connected/running."""
        pass


class RealUart(UartBase):
    """
    Real UART implementation using pyserial.
    Features auto-reconnect on disconnect.
    """
    
    def __init__(self, port: str, baud: int = 115200, reconnect_interval: float = 3.0):
        self.port = port
        self.baud = baud
        self.reconnect_interval = reconnect_interval
        
        self._serial = None
        self._running = False
        self._connected = False
        self._lock = threading.Lock()
        self._reconnect_thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """Start UART connection."""
        self._running = True
        self._connect()
        
        # Start reconnect monitor thread
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="uart-reconnect"
        )
        self._reconnect_thread.start()
    
    def stop(self) -> None:
        """Stop and close UART."""
        self._running = False
        with self._lock:
            if self._serial:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
            self._connected = False
    
    def _connect(self) -> bool:
        """Attempt to connect to serial port."""
        try:
            import serial
            with self._lock:
                if self._serial:
                    try:
                        self._serial.close()
                    except Exception:
                        pass
                
                self._serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baud,
                    timeout=0.1,  # Non-blocking read
                    write_timeout=1.0
                )
                self._connected = True
                logger.info(f"UART connected: {self.port} @ {self.baud}")
                return True
        except Exception as e:
            logger.warning(f"UART connect failed: {e}")
            self._connected = False
            return False
    
    def _reconnect_loop(self) -> None:
        """Background thread for auto-reconnect."""
        while self._running:
            if not self._connected:
                logger.info(f"Attempting UART reconnect to {self.port}...")
                self._connect()
            time.sleep(self.reconnect_interval)
    
    def read_line(self, timeout: float = 1.0) -> Optional[str]:
        """
        Read a line from serial port.
        
        Handles fragmentation by maintaining a persistent buffer across calls.
        """
        if not self._connected:
            return None
        
        # Use instance buffer to persist across calls
        if not hasattr(self, '_line_buffer'):
            self._line_buffer = b""
        
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            with self._lock:
                if not self._serial:
                    return None
                try:
                    # Read available data
                    chunk = self._serial.read(256)
                    if chunk:
                        self._line_buffer += chunk
                    
                    # Check if we have a complete line
                    if b'\n' in self._line_buffer:
                        line, self._line_buffer = self._line_buffer.split(b'\n', 1)
                        line_str = line.decode('utf-8', errors='replace').strip()
                        
                        # Filter out empty lines and CR-only lines
                        if line_str and line_str != '\r':
                            return line_str
                        # Continue reading if empty
                        
                except Exception as e:
                    logger.error(f"UART read error: {e}")
                    self._connected = False
                    self._line_buffer = b""
                    return None
            
            time.sleep(0.01)
        
        return None
    
    def write_line(self, line: str) -> bool:
        """Write a line to serial port."""
        if not self._connected:
            return False
        
        with self._lock:
            if not self._serial:
                return False
            try:
                data = line.encode('utf-8')
                if not data.endswith(b'\n'):
                    data += b'\n'
                self._serial.write(data)
                self._serial.flush()
                return True
            except Exception as e:
                logger.error(f"UART write error: {e}")
                self._connected = False
                return False
    
    @property
    def is_connected(self) -> bool:
        return self._connected


class FakeUart(UartBase):
    """
    Fake UART for testing without hardware.
    
    Emulates Coordinator protocol:
    - Emits @DATA telemetry every interval (Coordinator format: valve="open"/"closed")
    - Emits @INFO heartbeat periodically
    - Responds to @CMD with @ACK (Coordinator format with numeric id)
    - Maintains simulated valve state and mode
    """
    
    def __init__(
        self,
        data_interval: float = 1.0,
        info_interval: float = 10.0,
        drop_ack_prob: float = 0.0,
        initial_flow: float = 0.0,
        initial_battery: int = 100,
        initial_valve: str = "closed",  # Coordinator format
        initial_mode: str = MODE_AUTO
    ):
        self.data_interval = data_interval
        self.info_interval = info_interval
        self.drop_ack_prob = drop_ack_prob
        
        # Simulated state (Coordinator format)
        self._flow = initial_flow
        self._battery = initial_battery
        self._valve = initial_valve  # "open" or "closed"
        self._mode = initial_mode    # "auto" or "manual"
        self._valve_path = "auto"
        self._valve_known = True
        self._valve_node_id = "0x1234"
        self._uptime = 0
        
        # Simulated network info
        self._node_id = "0x0000"
        self._eui64 = "0011223344556677"
        self._pan_id = "0xBEEF"
        self._channel = 11
        self._tx_power = 8
        
        self._running = False
        self._rx_queue: queue.Queue = queue.Queue()
        self._data_thread: Optional[threading.Thread] = None
        self._info_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> None:
        """Start fake UART emulation."""
        self._running = True
        
        # Start @DATA emitter thread
        self._data_thread = threading.Thread(
            target=self._data_loop,
            daemon=True,
            name="fake-uart-data"
        )
        self._data_thread.start()
        
        # Start @INFO heartbeat thread
        self._info_thread = threading.Thread(
            target=self._info_loop,
            daemon=True,
            name="fake-uart-info"
        )
        self._info_thread.start()
        
        logger.info("FakeUart started (Coordinator emulation mode)")
    
    def stop(self) -> None:
        """Stop fake UART."""
        self._running = False
        logger.info("FakeUart stopped")
    
    def _data_loop(self) -> None:
        """Background thread emitting @DATA periodically (Coordinator format)."""
        while self._running:
            with self._lock:
                # Flow varies randomly when valve is open
                if self._valve == "open":
                    self._flow = round(random.uniform(100.0, 250.0), 0)  # Flow in units
                else:
                    self._flow = round(random.uniform(0.0, 5.0), 0)
                
                # Battery slowly drains
                if random.random() < 0.05:
                    self._battery = max(0, self._battery - 1)
                
                # Coordinator DATA format
                data = {
                    "flow": int(self._flow),
                    "valve": self._valve,  # "open" or "closed"
                    "battery": self._battery,
                    "mode": self._mode,
                    "tx_pending": False,
                    "valve_path": self._valve_path,
                    "valve_node_id": self._valve_node_id,
                    "valve_known": self._valve_known
                }
            
            line = make_data_line(data).strip()
            self._rx_queue.put(line)
            
            time.sleep(self.data_interval)
    
    def _info_loop(self) -> None:
        """Background thread emitting @INFO heartbeat (Coordinator format)."""
        while self._running:
            with self._lock:
                self._uptime += int(self.info_interval)
                
                # Coordinator INFO format
                info = {
                    "node_id": self._node_id,
                    "eui64": self._eui64,
                    "pan_id": self._pan_id,
                    "ch": self._channel,
                    "tx_power": self._tx_power,
                    "net_state": 2,  # FORMED
                    "uart_gateway": True,
                    "mode": self._mode,
                    "valve_path": self._valve_path,
                    "valve_known": self._valve_known,
                    "valve_eui64": "AABBCCDDEEFF0011",
                    "valve_node_id": self._valve_node_id,
                    "bind_index": 0,
                    "uptime": self._uptime
                }
            
            line = make_info_line(info).strip()
            self._rx_queue.put(line)
            
            time.sleep(self.info_interval)
    
    def read_line(self, timeout: float = 1.0) -> Optional[str]:
        """Read next line from fake UART queue."""
        try:
            return self._rx_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def write_line(self, line: str) -> bool:
        """
        Process a command line (Coordinator format).
        If it's a @CMD, update state and queue @ACK response.
        """
        line = line.strip()
        msg_type, payload = parse_uart_line(line)
        
        if msg_type == "CMD":
            return self._handle_cmd(payload)
        
        # Other types: just acknowledge write succeeded
        return True
    
    def _handle_cmd(self, payload: dict) -> bool:
        """
        Handle incoming @CMD (Coordinator format), update state, emit @ACK.
        
        Coordinator CMD format: {"id":N,"op":"valve_set","value":"open"}
        Coordinator ACK format: {"id":N,"ok":true,"msg":"valve set","valve":"open"}
        """
        cmd_id = payload.get("id", 0)
        op = payload.get("op", "")
        value = payload.get("value", "")
        
        # Simulate processing delay
        time.sleep(random.uniform(0.05, 0.2))
        
        # Check if we should drop ACK (simulate timeout)
        if random.random() < self.drop_ack_prob:
            logger.warning(f"FakeUart: Dropping ACK for id={cmd_id} (simulating timeout)")
            return True  # Write succeeded, but no ACK will come
        
        # Process command based on operation
        ok = True
        msg = ""
        extra_fields = {}
        
        if op == "valve_set":
            if self._mode == MODE_AUTO:
                ok = False
                msg = "rejected: AUTO mode"
            elif value in ("open", "closed", "close"):
                with self._lock:
                    self._valve = "closed" if value == "close" else value
                msg = "valve set"
                extra_fields["valve"] = self._valve
                logger.info(f"FakeUart: Valve set to {self._valve}")
            else:
                ok = False
                msg = "invalid value"
        
        elif op == "mode_set":
            if value in (MODE_AUTO, MODE_MANUAL):
                with self._lock:
                    self._mode = value
                msg = "mode set"
                extra_fields["mode"] = self._mode
                logger.info(f"FakeUart: Mode set to {self._mode}")
            else:
                ok = False
                msg = "invalid value"
        
        elif op == "info":
            msg = "info"
            # Also emit @INFO
            with self._lock:
                info = {
                    "node_id": self._node_id,
                    "eui64": self._eui64,
                    "pan_id": self._pan_id,
                    "ch": self._channel,
                    "tx_power": self._tx_power,
                    "net_state": 2,
                    "uart_gateway": True,
                    "mode": self._mode,
                    "valve_path": self._valve_path,
                    "valve_known": self._valve_known,
                    "valve_eui64": "AABBCCDDEEFF0011",
                    "valve_node_id": self._valve_node_id,
                    "bind_index": 0,
                    "uptime": self._uptime
                }
            info_line = make_info_line(info).strip()
            self._rx_queue.put(info_line)
        
        elif op == "threshold_set":
            close_th = payload.get("close_th", 0)
            open_th = payload.get("open_th", 0)
            if open_th >= close_th:
                ok = False
                msg = "open_th must be < close_th"
            else:
                msg = "threshold set"
                logger.info(f"FakeUart: Threshold set close={close_th}, open={open_th}")
        
        elif op == "valve_path_set":
            if value in ("auto", "direct", "binding"):
                with self._lock:
                    self._valve_path = value
                msg = "path set"
                logger.info(f"FakeUart: Valve path set to {value}")
            else:
                ok = False
                msg = "invalid value"
        
        else:
            ok = False
            msg = "unknown op"
        
        # Emit @ACK (Coordinator format)
        ack = {
            "id": cmd_id,
            "ok": ok,
            "msg": msg,
            **extra_fields
        }
        ack_line = make_ack_line(ack).strip()
        self._rx_queue.put(ack_line)
        
        return True
    
    @property
    def is_connected(self) -> bool:
        return self._running
    
    @property
    def state(self) -> dict:
        """Get current simulated state (for debugging)."""
        with self._lock:
            return {
                "flow": self._flow,
                "battery": self._battery,
                "valve": self._valve,
                "mode": self._mode,
                "valve_path": self._valve_path
            }
