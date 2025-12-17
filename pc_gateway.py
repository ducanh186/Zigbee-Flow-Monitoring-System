"""
Gateway Service - UART Communication Handler
Đọc dữ liệu từ Zigbee Coordinator qua UART và quản lý database
"""

import json
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable

import serial
import serial.tools.list_ports


class ZigbeeGateway:
    """Gateway service để giao tiếp với Zigbee Coordinator"""
    
    def __init__(self, db_path: str = "telemetry.db", port: Optional[str] = None, baudrate: int = 115200):
        self.db_path = db_path
        self.port = port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # State tracking
        self.last_data: Dict[str, Any] = {}
        self.last_seen: Optional[float] = None
        self.pending_acks: Dict[int, Dict[str, Any]] = {}  # cmd_id -> callback info
        self.next_cmd_id = 1
        
        # Callbacks
        self.on_data_callback: Optional[Callable] = None
        self.on_ack_callback: Optional[Callable] = None
        self.on_connection_change: Optional[Callable] = None
        
        # Initialize database
        self._init_database()
    
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
        """Kết nối tới serial port"""
        if port:
            self.port = port
        
        if not self.port:
            # Auto-detect port
            ports = self.list_ports()
            if not ports:
                return False
            self.port = ports[0][0]
        
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0,
                write_timeout=1.0
            )
            if self.on_connection_change:
                self.on_connection_change(True, self.port)
            return True
        except Exception as e:
            print(f"Connection error: {e}")
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
        return self.serial_conn is not None and self.serial_conn.is_open
    
    def _parse_line(self, line: str):
        """Parse một dòng từ UART"""
        line = line.strip()
        if not line:
            return
        
        # Match @DATA, @CMD, @ACK
        match = re.match(r'^@(DATA|CMD|ACK)\s+(.+)$', line)
        if not match:
            print(f"Unknown format: {line}")
            return
        
        msg_type = match.group(1)
        json_str = match.group(2)
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            return
        
        if msg_type == "DATA":
            self._handle_data(data)
        elif msg_type == "ACK":
            self._handle_ack(data)
        elif msg_type == "CMD":
            # Coordinator không nên gửi CMD, nhưng có thể log nếu cần
            print(f"Unexpected CMD from coordinator: {data}")
    
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE command_log
            SET ack_status = ?, ack_msg = ?, ack_at = ?
            WHERE cmd_id = ?
        """, ("ok" if ok else "fail", msg, datetime.now().isoformat(), cmd_id))
        conn.commit()
        conn.close()
        
        # Callback
        if self.on_ack_callback:
            self.on_ack_callback(data)
        
        # Pending ACK callback
        if cmd_id in self.pending_acks:
            callback = self.pending_acks[cmd_id].get("callback")
            if callback:
                callback(data)
            del self.pending_acks[cmd_id]
    
    def _read_loop(self):
        """Vòng lặp đọc dữ liệu từ serial"""
        while self.running:
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
                print(f"Read error: {e}")
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
    
    def send_command(self, operation: str, params: Dict[str, Any], callback: Optional[Callable] = None) -> int:
        """
        Gửi command xuống coordinator
        Returns: command ID
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to serial port")
        
        cmd_id = self.next_cmd_id
        self.next_cmd_id += 1
        
        cmd = {
            "id": cmd_id,
            "op": operation,
            **params
        }
        
        # Log to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO command_log (cmd_id, operation, params, sent_at)
            VALUES (?, ?, ?, ?)
        """, (cmd_id, operation, json.dumps(params), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        # Send via UART
        line = f"@CMD {json.dumps(cmd)}\n"
        self.serial_conn.write(line.encode('utf-8'))
        
        # Track pending ACK
        if callback:
            self.pending_acks[cmd_id] = {"callback": callback, "sent_at": time.time()}
        
        return cmd_id
    
    def set_valve(self, state: str, callback: Optional[Callable] = None) -> int:
        """Điều khiển valve: 'open' hoặc 'closed'"""
        return self.send_command("valve_set", {"value": state}, callback)
    
    def set_thresholds(self, close_th: int, open_th: int, callback: Optional[Callable] = None) -> int:
        """Đặt ngưỡng flow"""
        return self.send_command("threshold_set", {"close_th": close_th, "open_th": open_th}, callback)
    
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
    # Test gateway
    print("Available ports:")
    gateway = ZigbeeGateway()
    for port, desc in gateway.list_ports():
        print(f"  {port}: {desc}")
    
    def on_data(data):
        print(f"DATA: {data}")
    
    def on_ack(data):
        print(f"ACK: {data}")
    
    gateway.on_data_callback = on_data
    gateway.on_ack_callback = on_ack
    
    if gateway.connect():
        print(f"Connected to {gateway.port}")
        gateway.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            gateway.stop()
    else:
        print("Failed to connect")
