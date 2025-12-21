"""
Gateway Service - UART Communication Handler
Đọc dữ liệu từ Zigbee Coordinator qua UART và quản lý database
"""

import argparse
import json
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable, TextIO
from queue import Queue, Empty

import serial
import serial.tools.list_ports


class ZigbeeGateway:
    """Gateway service để giao tiếp với Zigbee Coordinator"""
    
    def __init__(self, db_path: str = "telemetry.db", port: Optional[str] = None, 
                 baudrate: int = 115200, stdin_mode: bool = False, verbose: bool = True):
        self.db_path = db_path
        self.port = port
        self.baudrate = baudrate
        self.stdin_mode = stdin_mode
        self.verbose = verbose
        self.serial_conn: Optional[serial.Serial] = None
        self.stdin_stream: Optional[TextIO] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # State tracking
        self.last_data: Dict[str, Any] = {}
        self.last_seen: Optional[float] = None
        self.pending_acks: Dict[int, Queue] = {}  # cmd_id -> Queue for ACK response
        self.next_cmd_id = 1
        self.ack_timeout = 2.0  # seconds
        
        # Callbacks
        self.on_data_callback: Optional[Callable] = None
        self.on_ack_callback: Optional[Callable] = None
        self.on_connection_change: Optional[Callable] = None
        
        # Initialize database
        self._init_database()
    
    def _log(self, msg: str):
        """Internal logging - only if verbose"""
        if self.verbose:
            print(f"[Gateway] {msg}")
    
    def _normalize_json(self, json_str: str) -> str:
        """
        Attempt to normalize non-strict JSON like {flow:100, valve:open}
        to strict JSON {"flow":100, "valve":"open"}
        """
        # First try strict parsing
        try:
            json.loads(json_str)
            return json_str  # Already valid
        except json.JSONDecodeError:
            pass
        
        # Try to fix unquoted keys and string values
        # Pattern: word followed by colon (unquoted key)
        fixed = re.sub(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', json_str)
        
        # Pattern: unquoted string values (between : and , or })
        # This is tricky - match :value patterns where value is not a number/bool/null
        def quote_value(match):
            value = match.group(1).strip()
            # Don't quote if it's a number, true, false, null, or already quoted
            if value in ('true', 'false', 'null') or value.startswith('"') or value.startswith('[') or value.startswith('{'):
                return match.group(0)
            try:
                float(value)
                return match.group(0)  # It's a number
            except ValueError:
                return f':"{value}"'
        
        fixed = re.sub(r':\s*([^,}\s]+)\s*([,}])', lambda m: quote_value(m) + m.group(2), fixed)
        
        return fixed
    
    def _init_database(self):
        """Khởi tạo SQLite database với schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Telemetry table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                flow INTEGER NOT NULL,
                battery INTEGER NOT NULL,
                valve TEXT NOT NULL,
                received_at TEXT NOT NULL
            )
        """)
        
        # Command log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cmd_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                params TEXT NOT NULL,
                ack_status TEXT,
                ack_msg TEXT,
                sent_at TEXT NOT NULL,
                ack_at TEXT
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cmd_log_cmd_id ON command_log(cmd_id)")
        
        conn.commit()
        conn.close()
    
    def list_ports(self):
        """Liệt kê các COM port khả dụng"""
        ports = serial.tools.list_ports.comports()
        return [(p.device, p.description) for p in ports]
    
    def connect(self, port: Optional[str] = None) -> bool:
        """Kết nối tới serial port hoặc stdin"""
        if self.stdin_mode:
            self.stdin_stream = sys.stdin
            self._log("Reading from stdin")
            if self.on_connection_change:
                self.on_connection_change(True, "stdin")
            return True
        
        if port:
            self.port = port
        
        if not self.port:
            # Auto-detect port
            ports = self.list_ports()
            if not ports:
                self._log("No serial ports found")
                return False
            self.port = ports[0][0]
            self._log(f"Auto-selected port: {self.port}")
        
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0,
                write_timeout=1.0
            )
            self._log(f"Connected to {self.port} @ {self.baudrate} baud")
            if self.on_connection_change:
                self.on_connection_change(True, self.port)
            return True
        except Exception as e:
            self._log(f"Connection error: {e}")
            if self.on_connection_change:
                self.on_connection_change(False, str(e))
            return False
    
    def disconnect(self):
        """Ngắt kết nối serial"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.serial_conn = None
        if self.on_connection_change:
            self.on_connection_change(False, "Disconnected")
    
    def is_connected(self) -> bool:
        """Kiểm tra trạng thái kết nối"""
        if self.stdin_mode:
            return self.stdin_stream is not None
        return self.serial_conn is not None and self.serial_conn.is_open
    
    def _parse_line(self, line: str):
        """Parse một dòng từ UART"""
        line = line.strip()
        if not line:
            return
        
        # Match @DATA, @CMD, @ACK
        match = re.match(r'^@(DATA|CMD|ACK)\s+(.+)$', line)
        if not match:
            # Ignore noise lines silently
            return
        
        msg_type = match.group(1)
        json_str = match.group(2)
        
        # Try to normalize non-strict JSON
        json_str = self._normalize_json(json_str)
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            self._log(f"JSON parse error on line: {line[:50]}... - {e}")
            return
        
        if self.verbose:
            self._log(f"RX @{msg_type} {json.dumps(data)}")
        
        if msg_type == "DATA":
            self._handle_data(data)
        elif msg_type == "ACK":
            self._handle_ack(data)
        elif msg_type == "CMD":
            # Coordinator không nên gửi CMD, nhưng có thể log nếu cần
            self._log(f"Unexpected CMD from coordinator: {data}")
    
    def _handle_data(self, data: Dict[str, Any]):
        """Xử lý @DATA message"""
        self.last_seen = time.time()
        self.last_data = data
        
        # Extract fields
        flow = data.get("flow", 0)
        battery = data.get("battery", 0)
        valve = data.get("valve", "unknown")
        ts = data.get("ts", time.time())
        
        # Save to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO telemetry (ts, flow, battery, valve, received_at)
            VALUES (?, ?, ?, ?, ?)
        """, (ts, flow, battery, valve, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        # Callback
        if self.on_data_callback:
            self.on_data_callback(data)
    
    def _handle_ack(self, data: Dict[str, Any]):
        """Xử lý @ACK message"""
        cmd_id = data.get("id")
        ok = data.get("ok", False)
        msg = data.get("msg", "")
        
        # Update command log
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE command_log
                SET ack_status = ?, ack_msg = ?, ack_at = ?
                WHERE cmd_id = ?
            """, ("ok" if ok else "fail", msg, datetime.now().isoformat(), cmd_id))
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"Database error logging ACK: {e}")
        
        # Callback
        if self.on_ack_callback:
            self.on_ack_callback(data)
        
        # Wake up pending synchronous caller
        if cmd_id in self.pending_acks:
            queue = self.pending_acks[cmd_id]
            queue.put(data)
            # Don't delete yet - let send_command handle cleanup after timeout
    
    def _read_loop(self):
        """Vòng lặp đọc dữ liệu từ serial hoặc stdin"""
        while self.running:
            if self.stdin_mode:
                # Read from stdin
                try:
                    line = self.stdin_stream.readline()
                    if not line:  # EOF
                        self._log("EOF on stdin, stopping")
                        self.running = False
                        break
                    self._parse_line(line)
                except Exception as e:
                    self._log(f"Stdin read error: {e}")
                    break
            else:
                # Read from serial
                if not self.is_connected():
                    time.sleep(1.0)
                    # Try reconnect
                    if self.port:
                        self.connect(self.port)
                    continue
                
                try:
                    if self.serial_conn.in_waiting > 0:
                        line = self.serial_conn.readline().decode('utf-8', errors='ignore')
                        self._parse_line(line)
                    else:
                        time.sleep(0.01)
                except Exception as e:
                    self._log(f"Serial read error: {e}")
                    self.disconnect()
                    time.sleep(1.0)
    
    def start(self):
        """Bắt đầu gateway service"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Dừng gateway service"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self.disconnect()
    
    def send_command(self, operation: str, params: Dict[str, Any], 
                    wait_ack: bool = True, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Gửi command xuống coordinator
        
        Args:
            operation: Command operation (e.g., 'valve_set')
            params: Command parameters
            wait_ack: If True, wait for ACK synchronously
            timeout: ACK timeout in seconds (default: self.ack_timeout)
        
        Returns:
            Dictionary with:
                - cmd_id: Command ID sent
                - ok: True if ACK received with ok=true, False otherwise
                - msg: ACK message
                - ack: Full ACK payload (if received)
        
        Raises:
            ConnectionError: If not connected
            TimeoutError: If wait_ack=True and no ACK received within timeout
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to serial port")
        
        if self.stdin_mode and wait_ack:
            # Can't send commands in stdin mode
            raise RuntimeError("Cannot send commands in stdin mode")
        
        cmd_id = self.next_cmd_id
        self.next_cmd_id += 1
        
        cmd = {
            "id": cmd_id,
            "op": operation,
            **params
        }
        
        # Log to database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO command_log (cmd_id, operation, params, sent_at)
                VALUES (?, ?, ?, ?)
            """, (cmd_id, operation, json.dumps(params), datetime.now().isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            self._log(f"Database error logging command: {e}")
        
        # Setup ACK queue if waiting
        ack_queue = None
        if wait_ack:
            ack_queue = Queue()
            self.pending_acks[cmd_id] = ack_queue
        
        # Send via UART
        line = f"@CMD {json.dumps(cmd)}\n"
        try:
            self.serial_conn.write(line.encode('utf-8'))
            self._log(f"Sent @CMD id={cmd_id} op={operation}")
        except Exception as e:
            if cmd_id in self.pending_acks:
                del self.pending_acks[cmd_id]
            raise ConnectionError(f"Failed to send command: {e}")
        
        # Wait for ACK if requested
        if wait_ack:
            timeout_val = timeout if timeout is not None else self.ack_timeout
            try:
                ack_data = ack_queue.get(timeout=timeout_val)
                del self.pending_acks[cmd_id]
                
                return {
                    "cmd_id": cmd_id,
                    "ok": ack_data.get("ok", False),
                    "msg": ack_data.get("msg", ""),
                    "ack": ack_data
                }
            except Empty:
                if cmd_id in self.pending_acks:
                    del self.pending_acks[cmd_id]
                self._log(f"ACK timeout for cmd_id={cmd_id}")
                raise TimeoutError(f"No ACK received for command id={cmd_id} within {timeout_val}s")
        
        return {"cmd_id": cmd_id, "ok": None, "msg": "Command sent (no ACK wait)"}
    
    def set_valve(self, state: str, wait_ack: bool = True) -> Dict[str, Any]:
        """
        Điều khiển valve: 'open' hoặc 'closed'
        
        Args:
            state: "open" or "closed"
            wait_ack: If True, wait for ACK (default)
        
        Returns:
            Result dict with ok, msg, ack fields
        """
        if state not in ("open", "closed"):
            raise ValueError(f"Invalid valve state: {state}. Must be 'open' or 'closed'")
        return self.send_command("valve_set", {"value": state}, wait_ack=wait_ack)
    
    def set_thresholds(self, close_th: int, open_th: int, wait_ack: bool = True) -> Dict[str, Any]:
        """
        Đặt ngưỡng flow
        
        Args:
            close_th: Flow threshold to close valve
            open_th: Flow threshold to open valve
            wait_ack: If True, wait for ACK (default)
        
        Returns:
            Result dict with ok, msg, ack fields
        """
        return self.send_command("threshold_set", 
                                {"close_th": close_th, "open_th": open_th}, 
                                wait_ack=wait_ack)
    
    def get_telemetry_range(self, start_ts: float, end_ts: float):
        """Lấy telemetry trong khoảng thời gian"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ts, flow, battery, valve
            FROM telemetry
            WHERE ts >= ? AND ts <= ?
            ORDER BY ts
        """, (start_ts, end_ts))
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    def get_telemetry_last_n(self, n: int = 100):
        """Lấy n records telemetry gần nhất"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ts, flow, battery, valve
            FROM telemetry
            ORDER BY id DESC
            LIMIT ?
        """, (n,))
        rows = cursor.fetchall()
        conn.close()
        return list(reversed(rows))
    
    def get_aggregated_data(self, interval: str, limit: int = 100):
        """
        Lấy dữ liệu aggregated theo interval
        interval: 'minute', 'hour', 'day'
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if interval == 'minute':
            group_by = "datetime(ts, 'unixepoch', 'localtime', 'start of day', printf('%d minutes', (strftime('%M', datetime(ts, 'unixepoch', 'localtime')) / 5) * 5))"
        elif interval == 'hour':
            group_by = "datetime(ts, 'unixepoch', 'localtime', 'start of hour')"
        elif interval == 'day':
            group_by = "date(ts, 'unixepoch', 'localtime')"
        else:
            group_by = "datetime(ts, 'unixepoch', 'localtime', 'start of hour')"
        
        query = f"""
            SELECT 
                strftime('%s', {group_by}) as bucket_ts,
                AVG(flow) as avg_flow,
                MAX(flow) as max_flow,
                MIN(flow) as min_flow,
                AVG(battery) as avg_battery
            FROM telemetry
            GROUP BY {group_by}
            ORDER BY bucket_ts DESC
            LIMIT ?
        """
        
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return list(reversed(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Zigbee Gateway - UART bridge for Coordinator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available ports
  python pc_gateway.py
  
  # Connect to specific port
  python pc_gateway.py --port COM5
  
  # Connect with custom baud rate
  python pc_gateway.py --port COM5 --baud 9600
  
  # Read from stdin (for testing with fake_device)
  python fake_device.py --mode console | python pc_gateway.py --stdin
  
  # One-shot valve command
  python pc_gateway.py --port COM5 --send open
  python pc_gateway.py --port COM5 --send closed
        """
    )
    parser.add_argument("--port", type=str, help="Serial port (e.g., COM5 or /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--stdin", action="store_true", help="Read from stdin instead of serial")
    parser.add_argument("--send", type=str, choices=["open", "closed"], 
                       help="One-shot: send valve command and exit")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose logging")
    parser.add_argument("--db", type=str, default="telemetry.db", help="Database path")
    
    args = parser.parse_args()
    
    # If no args, show available ports
    if len(sys.argv) == 1:
        gateway = ZigbeeGateway(verbose=False)
        ports = gateway.list_ports()
        if ports:
            print("Available serial ports:")
            for port, desc in ports:
                print(f"  {port}: {desc}")
        else:
            print("No serial ports found")
        print("\nUse --help for usage options")
        sys.exit(0)
    
    # Create gateway
    gateway = ZigbeeGateway(
        db_path=args.db,
        port=args.port,
        baudrate=args.baud,
        stdin_mode=args.stdin,
        verbose=not args.quiet
    )
    
    # One-shot send mode
    if args.send:
        if args.stdin:
            print("Error: Cannot use --send with --stdin")
            sys.exit(1)
        
        if not gateway.connect():
            print(f"Failed to connect to {args.port}")
            sys.exit(1)
        
        gateway.start()
        time.sleep(0.5)  # Give thread time to start
        
        try:
            print(f"Sending valve {args.send}...")
            result = gateway.set_valve(args.send, wait_ack=True)
            
            if result["ok"]:
                print(f"✓ Success: {result['msg']}")
                sys.exit(0)
            else:
                print(f"✗ Failed: {result['msg']}")
                sys.exit(1)
        except TimeoutError as e:
            print(f"✗ Timeout: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"✗ Error: {e}")
            sys.exit(1)
        finally:
            gateway.stop()
    
    # Normal continuous mode
    def on_data(data):
        if not args.quiet:
            print(f"📊 Flow={data.get('flow')} L/min, Battery={data.get('battery')}%, Valve={data.get('valve')}")
    
    def on_ack(data):
        if not args.quiet:
            status = "✓" if data.get("ok") else "✗"
            print(f"{status} ACK id={data.get('id')}: {data.get('msg')}")
    
    gateway.on_data_callback = on_data
    gateway.on_ack_callback = on_ack
    
    if not gateway.connect():
        print(f"Failed to connect")
        sys.exit(1)
    
    gateway.start()
    
    try:
        print("Gateway running. Press Ctrl+C to stop...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
        gateway.stop()
        print("Stopped.")


# ==============================================================================
# MANUAL TEST STEPS (COMMENTED REFERENCE)
# ==============================================================================
#
# 1. List available ports:
#    python pc_gateway.py
#
# 2. Test with fake device (stdin mode):
#    python fake_device.py --mode console | python pc_gateway.py --stdin
#    Expected: Should see @DATA messages being received and logged
#
# 3. Connect to real serial port:
#    python pc_gateway.py --port COM5
#    Expected: "Connected to COM5 @ 115200 baud"
#             Flow/battery metrics appear as coordinator sends @DATA
#
# 4. One-shot valve control test:
#    python pc_gateway.py --port COM5 --send open
#    Expected: "✓ Success: valve opened" (or similar ACK message)
#    
#    python pc_gateway.py --port COM5 --send closed
#    Expected: "✓ Success: valve closed"
#
# 5. Integration with dashboard:
#    Terminal 1: python pc_gateway.py --port COM5
#    Terminal 2: streamlit run dashboard.py
#    Expected: Dashboard imports ZigbeeGateway without errors
#             Dashboard can call gateway.set_valve("open"/"closed")
#             get_telemetry_last_n() returns recent data
#
# 6. Database verification:
#    sqlite3 telemetry.db
#    sqlite> SELECT COUNT(*) FROM telemetry;
#    sqlite> SELECT * FROM telemetry ORDER BY id DESC LIMIT 5;
#    Expected: Rows inserted with flow, battery, valve, timestamps
#
# 7. Graceful shutdown:
#    Run gateway, press Ctrl+C
#    Expected: "Shutting down gracefully..." followed by clean exit
#
# ==============================================================================

