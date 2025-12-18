"""Quick test to read raw data from COM with multiple baudrates"""
import serial
import time

PORTS = ["COM7", "COM6"]  # Test both ports
BAUDRATES = [115200, 9600, 19200, 38400, 57600, 76800, 230400, 460800, 921600]  # Extended list
TEST_DURATION = 3  # seconds per baudrate (shorter for more tests)

print("=" * 70)
print("TESTING MULTIPLE PORTS & BAUDRATES")
print("=" * 70)

for port in PORTS:
    print(f"\n{'='*70}")
    print(f"PORT: {port}")
    print(f"{'='*70}")
    
    for baud in BAUDRATES:
        print(f"\n  [{baud:>6} baud]", end=" ")
        
        try:
            ser = serial.Serial(port, baud, timeout=0.5)
            
            start = time.time()
            line_count = 0
            byte_count = 0
            sample_lines = []
            
            while time.time() - start < TEST_DURATION:
                if ser.in_waiting > 0:
                    raw = ser.readline()
                    byte_count += len(raw)
                    line = raw.decode('utf-8', errors='ignore').strip()
                    if line:
                        line_count += 1
                        if len(sample_lines) < 2:  # Keep first 2 lines
                            sample_lines.append(line[:60])
                else:
                    time.sleep(0.01)
            
            ser.close()
            
            if byte_count > 0:
                print(f"→ {line_count} lines, {byte_count} bytes")
                if line_count > 0:
                    print(f"      ✓✓✓ DATA RECEIVED! ✓✓✓")
                    for i, sample in enumerate(sample_lines, 1):
                        print(f"      Sample {i}: {sample}")
            else:
                print(f"→ No data")
            
        except serial.SerialException as e:
            print(f"→ Error: {e}")
        except Exception as e:
            print(f"→ Error: {e}")

print("\n" + "=" * 70)
print("DONE. Look for lines marked with ✓✓✓ above.")
print("=" * 70)
