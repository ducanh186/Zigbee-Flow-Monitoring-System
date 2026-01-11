"""
Direct CLI Test for Coordinator
Test if Coordinator responds to @CMD commands
"""

import serial
import time
import json

COM_PORT = "COM10"
BAUD_RATE = 115200

def test_cli():
    print("=" * 60)
    print("Coordinator CLI Test")
    print("=" * 60)
    
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=2)
        print(f"✓ Connected to {COM_PORT} @ {BAUD_RATE}")
        time.sleep(0.5)
        
        # Clear buffer
        ser.reset_input_buffer()
        
        tests = [
            # Test 1: Info command
            {
                "cmd": '@CMD {"id":99,"op":"info"}\n',
                "desc": "Get system info"
            },
            # Test 2: Valve set OPEN
            {
                "cmd": '@CMD {"id":100,"op":"valve_set","value":"open"}\n',
                "desc": "Valve OPEN"
            },
            # Test 3: Valve set CLOSE
            {
                "cmd": '@CMD {"id":101,"op":"valve_set","value":"closed"}\n',
                "desc": "Valve CLOSE"
            },
            # Test 4: Mode check
            {
                "cmd": '@CMD {"id":102,"op":"mode_set","value":"manual"}\n',
                "desc": "Set mode to MANUAL"
            },
        ]
        
        for i, test in enumerate(tests, 1):
            print(f"\n--- Test {i}: {test['desc']} ---")
            print(f"TX: {test['cmd'].strip()}")
            
            ser.write(test['cmd'].encode())
            ser.flush()
            
            # Wait and read response
            time.sleep(0.5)
            
            responses = []
            start = time.time()
            while time.time() - start < 2:
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        responses.append(line)
                        print(f"RX: {line}")
                        if "@ACK" in line or "@INFO" in line or "@DATA" in line:
                            break
                time.sleep(0.1)
            
            if not responses:
                print("⚠ NO RESPONSE!")
            
            time.sleep(0.3)
        
        # Monitor for a few seconds to see any @DATA
        print("\n--- Monitoring for @DATA (5 seconds) ---")
        start = time.time()
        while time.time() - start < 5:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"RX: {line}")
            time.sleep(0.1)
        
        ser.close()
        print("\n✓ Test complete")
        
    except serial.SerialException as e:
        print(f"✗ Serial error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    test_cli()
