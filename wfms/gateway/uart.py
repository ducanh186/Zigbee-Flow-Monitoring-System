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

from common.proto import make_data_line, make_ack_line, parse_uart_line, now_ts

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
        """Read a line from serial port."""
        if not self._connected:
            return None
        
        deadline = time.time() + timeout
        buffer = b""
        
        while time.time() < deadline:
            with self._lock:
                if not self._serial:
                    return None
                try:
                    chunk = self._serial.read(256)
                    if chunk:
                        buffer += chunk
                        if b'\n' in buffer:
                            line, _ = buffer.split(b'\n', 1)
                            return line.decode('utf-8', errors='replace').strip()
                except Exception as e:
                    logger.error(f"UART read error: {e}")
                    self._connected = False
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
    
    - Emits @DATA telemetry every interval
    - Responds to @CMD with @ACK (optionally drops ACK to simulate timeout)
    - Maintains simulated valve state
    """
    
    def __init__(
        self,
        data_interval: float = 1.0,
        drop_ack_prob: float = 0.0,
        initial_flow: float = 0.0,
        initial_battery: int = 100,
        initial_valve: str = "OFF"
    ):
        self.data_interval = data_interval
        self.drop_ack_prob = drop_ack_prob
        
        # Simulated state
        self._flow = initial_flow
        self._battery = initial_battery
        self._valve = initial_valve
        
        self._running = False
        self._rx_queue: queue.Queue = queue.Queue()
        self._data_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> None:
        """Start fake UART emulation."""
        self._running = True
        self._data_thread = threading.Thread(
            target=self._data_loop,
            daemon=True,
            name="fake-uart-data"
        )
        self._data_thread.start()
        logger.info("FakeUart started (emulation mode)")
    
    def stop(self) -> None:
        """Stop fake UART."""
        self._running = False
        logger.info("FakeUart stopped")
    
    def _data_loop(self) -> None:
        """Background thread emitting @DATA periodically."""
        while self._running:
            # Simulate flow variation
            with self._lock:
                # Flow varies randomly when valve is ON
                if self._valve == "ON":
                    self._flow = round(random.uniform(10.0, 25.0), 1)
                else:
                    self._flow = round(random.uniform(0.0, 0.5), 1)
                
                # Battery slowly drains
                if random.random() < 0.05:
                    self._battery = max(0, self._battery - 1)
                
                data = {
                    "flow": self._flow,
                    "battery": self._battery,
                    "valve": self._valve,
                    "ts": now_ts()
                }
            
            line = make_data_line(data).strip()
            self._rx_queue.put(line)
            
            time.sleep(self.data_interval)
    
    def read_line(self, timeout: float = 1.0) -> Optional[str]:
        """Read next line from fake UART queue."""
        try:
            return self._rx_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def write_line(self, line: str) -> bool:
        """
        Process a command line.
        If it's a @CMD, update state and queue @ACK response.
        """
        line = line.strip()
        msg_type, payload = parse_uart_line(line)
        
        if msg_type == "CMD":
            return self._handle_cmd(payload)
        
        # Other types: just acknowledge write succeeded
        return True
    
    def _handle_cmd(self, payload: dict) -> bool:
        """Handle incoming @CMD, update state, emit @ACK."""
        cid = payload.get("cid", "unknown")
        value = payload.get("value")
        
        # Simulate processing delay
        time.sleep(random.uniform(0.05, 0.2))
        
        # Check if we should drop ACK (simulate timeout)
        if random.random() < self.drop_ack_prob:
            logger.warning(f"FakeUart: Dropping ACK for cid={cid} (simulating timeout)")
            return True  # Write succeeded, but no ACK will come
        
        # Update valve state
        ok = True
        reason = ""
        
        if value in ("ON", "OFF"):
            with self._lock:
                self._valve = value
            logger.info(f"FakeUart: Valve set to {value}")
        else:
            ok = False
            reason = "invalid_value"
        
        # Emit @ACK
        ack = {
            "cid": cid,
            "ok": ok,
            "reason": reason,
            "ts": now_ts()
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
                "valve": self._valve
            }
