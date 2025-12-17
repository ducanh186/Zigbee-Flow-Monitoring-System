"""
Fake Data Generator - Để test dashboard khi chưa có firmware
Generate dữ liệu @DATA giả lập qua virtual serial port hoặc file
"""

import json
import random
import time
import sys
from datetime import datetime


class FakeZigbeeDevice:
    """Giả lập Zigbee Coordinator gửi dữ liệu"""
    
    def __init__(self, mode="console"):
        """
        mode: 'console' (print ra stdout) hoặc 'file' (ghi vào file)
        """
        self.mode = mode
        self.flow = 50  # Initial flow
        self.battery = 100  # Initial battery
        self.valve = "open"  # Initial valve state
        self.close_threshold = 80
        self.open_threshold = 20
        self.protocol_version = 1
        
        if mode == "file":
            self.output_file = open("fake_serial.txt", "a")
    
    def generate_telemetry(self):
        """Generate một @DATA message"""
        # Simulate flow variations
        self.flow += random.randint(-10, 10)
        self.flow = max(0, min(200, self.flow))  # Clamp 0-200
        
        # Simulate battery drain (very slow)
        if random.random() < 0.01:  # 1% chance to decrease
            self.battery = max(0, self.battery - 1)
        
        # Auto valve logic
        if self.flow >= self.close_threshold and self.valve == "open":
            self.valve = "closed"
            print(f"[AUTO] Flow {self.flow} >= {self.close_threshold}, closing valve", file=sys.stderr)
        elif self.flow <= self.open_threshold and self.valve == "closed":
            self.valve = "open"
            print(f"[AUTO] Flow {self.flow} <= {self.open_threshold}, opening valve", file=sys.stderr)
        
        data = {
            "v": self.protocol_version,
            "ts": int(time.time()),
            "flow": self.flow,
            "battery": self.battery,
            "valve": self.valve
        }
        
        return f"@DATA {json.dumps(data)}"
    
    def send_telemetry(self):
        """Gửi telemetry message"""
        msg = self.generate_telemetry()
        
        if self.mode == "console":
            print(msg, flush=True)
        elif self.mode == "file":
            self.output_file.write(msg + "\n")
            self.output_file.flush()
    
    def handle_command(self, cmd_line):
        """Xử lý command từ stdin"""
        try:
            if not cmd_line.startswith("@CMD "):
                return
            
            json_str = cmd_line[5:].strip()
            cmd = json.loads(json_str)
            
            cmd_id = cmd.get("id", 0)
            op = cmd.get("op", "")
            
            if op == "valve_set":
                value = cmd.get("value", "")
                if value in ["open", "closed"]:
                    self.valve = value
                    ack = {
                        "id": cmd_id,
                        "ok": True,
                        "msg": f"valve set to {value}",
                        "valve": value
                    }
                    print(f"[CMD] Valve set to {value}", file=sys.stderr)
                else:
                    ack = {
                        "id": cmd_id,
                        "ok": False,
                        "msg": "invalid valve state"
                    }
            
            elif op == "threshold_set":
                close_th = cmd.get("close_th", 80)
                open_th = cmd.get("open_th", 20)
                
                if 0 <= open_th <= close_th <= 999:
                    self.close_threshold = close_th
                    self.open_threshold = open_th
                    ack = {
                        "id": cmd_id,
                        "ok": True,
                        "msg": "thresholds saved",
                        "close_th": close_th,
                        "open_th": open_th
                    }
                    print(f"[CMD] Thresholds set: close={close_th}, open={open_th}", file=sys.stderr)
                else:
                    ack = {
                        "id": cmd_id,
                        "ok": False,
                        "msg": "invalid threshold range"
                    }
            
            else:
                ack = {
                    "id": cmd_id,
                    "ok": False,
                    "msg": f"unknown operation: {op}"
                }
            
            # Send ACK
            ack_msg = f"@ACK {json.dumps(ack)}"
            if self.mode == "console":
                print(ack_msg, flush=True)
            elif self.mode == "file":
                self.output_file.write(ack_msg + "\n")
                self.output_file.flush()
        
        except Exception as e:
            print(f"[ERROR] Command parse error: {e}", file=sys.stderr)
    
    def run(self, interval=2.0):
        """Chạy fake device"""
        print("[FAKE] Starting fake Zigbee device...", file=sys.stderr)
        print(f"[FAKE] Mode: {self.mode}, Interval: {interval}s", file=sys.stderr)
        
        try:
            last_telemetry = 0
            while True:
                current_time = time.time()
                
                # Send telemetry every interval
                if current_time - last_telemetry >= interval:
                    self.send_telemetry()
                    last_telemetry = current_time
                
                # Check for commands (non-blocking)
                # Note: stdin.readline() is blocking, so this is simplified
                # For real implementation, use select() or threading
                
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            print("\n[FAKE] Stopped", file=sys.stderr)
        finally:
            if self.mode == "file":
                self.output_file.close()
    
    def close(self):
        if self.mode == "file" and hasattr(self, 'output_file'):
            self.output_file.close()


def generate_sample_data_file(filename="sample_data.txt", count=100):
    """Generate một file chứa sample data để test"""
    print(f"Generating {count} sample records to {filename}...")
    
    with open(filename, "w") as f:
        fake = FakeZigbeeDevice()
        for i in range(count):
            msg = fake.generate_telemetry()
            f.write(msg + "\n")
            
            # Random valve commands
            if i % 20 == 0:
                cmd_id = i // 20 + 1
                valve_state = "closed" if fake.valve == "open" else "open"
                fake.valve = valve_state
                ack = {
                    "id": cmd_id,
                    "ok": True,
                    "msg": f"valve set to {valve_state}",
                    "valve": valve_state
                }
                f.write(f"@ACK {json.dumps(ack)}\n")
            
            time.sleep(0.01)
    
    print(f"Generated {count} records to {filename}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fake Zigbee Device Simulator")
    parser.add_argument("--mode", choices=["console", "file", "sample"], default="console",
                       help="Output mode: console (stdout), file (fake_serial.txt), or sample (generate file)")
    parser.add_argument("--interval", type=float, default=2.0,
                       help="Telemetry interval in seconds (default: 2.0)")
    parser.add_argument("--count", type=int, default=100,
                       help="Number of sample records to generate (sample mode only)")
    
    args = parser.parse_args()
    
    if args.mode == "sample":
        generate_sample_data_file(count=args.count)
    else:
        fake_device = FakeZigbeeDevice(mode=args.mode)
        fake_device.run(interval=args.interval)
