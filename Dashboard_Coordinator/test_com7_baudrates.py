#!/usr/bin/env python3
"""
Test COM7 at different baudrates to see what data is received.
"""
import serial
import time

PORT = "COM7"
BAUDRATES = [9600, 19200, 38400, 57600, 115200]
TEST_DURATION = 2  # seconds per baudrate (shorter for quick test)

print(f"Testing {PORT} at various baudrates...")
print(f"Each test will run for {TEST_DURATION} seconds\n")

for baud in BAUDRATES:
    print(f"{'='*60}")
    print(f"Testing baudrate: {baud}")
    print(f"{'='*60}")
    
    try:
        ser = serial.Serial(port=PORT, baudrate=baud, timeout=1)
        print(f"✓ Port opened successfully at {baud} baud")
        
        lines_received = 0
        start_time = time.time()
        
        while time.time() - start_time < TEST_DURATION:
            raw = ser.readline()
            if raw:
                try:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if line:
                        lines_received += 1
                        print(f"  [{lines_received}] {line}")
                except Exception as e:
                    print(f"  [ERROR] Decode error: {e}")
        
        ser.close()
        
        if lines_received == 0:
            print(f"✗ No data received at {baud} baud")
        else:
            print(f"✓ Received {lines_received} lines at {baud} baud")
            
    except serial.SerialException as e:
        print(f"✗ Failed to open port: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print()
    time.sleep(0.5)

print("="*60)
print("Test completed!")
