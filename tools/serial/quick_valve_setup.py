"""
Quick Valve Setup - Use existing binding
"""

import serial
import time

COM_PORT = "COM10"
BAUD_RATE = 115200

def send(ser, cmd):
    print(f"TX: {cmd.strip()}")
    time.sleep(0.5)
    ser.write(cmd.encode())
    time.sleep(1.5)
    
    while ser.in_waiting:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if line and any(x in line for x in ["@ACK", "@INFO", "@DATA"]):
            print(f"RX: {line}")

print("=" * 60)
print("Configuring Valve Control via Binding")
print("=" * 60)

ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=2)
print(f"✓ Connected\n")
time.sleep(1)

# 1. Set mode to MANUAL
send(ser, '@CMD {"id":1,"op":"mode_set","value":"manual"}\n')

# 2. Set valve path to BINDING
send(ser, '@CMD {"id":2,"op":"valve_path_set","value":"binding"}\n')

# 3. Pair valve (bind_index=0 from binding table)
send(ser, '@CMD {"id":3,"op":"valve_pair","eui64":"0000000000000054","node_id":"0x1D34","bind_index":0}\n')

# 4. Check status
send(ser, '@CMD {"id":4,"op":"info"}\n')

print("\n" + "=" * 60)
print("Testing Valve Control")
print("=" * 60)

# 5. Test OPEN
send(ser, '@CMD {"id":10,"op":"valve_set","value":"open"}\n')
time.sleep(2)

# 6. Test CLOSE
send(ser, '@CMD {"id":11,"op":"valve_set","value":"closed"}\n')
time.sleep(2)

# Final check
send(ser, '@CMD {"id":99,"op":"info"}\n')

ser.close()
print("\n✅ Done!")
