"""
Set Valve Target on Coordinator
"""

import serial
import time

COM_PORT = "COM10"
BAUD_RATE = 115200
VALVE_EUI64 = "0000000000000054"

def send_cmd(ser, cmd, desc, wait=1.0):
    print(f"\n--- {desc} ---")
    print(f"TX: {cmd.strip()}")
    
    ser.reset_input_buffer()
    ser.write(cmd.encode())
    ser.flush()
    
    time.sleep(0.3)
    
    responses = []
    start = time.time()
    while time.time() - start < wait:
        if ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                responses.append(line)
                # Only print relevant lines
                if any(x in line for x in ["@ACK", "@INFO", "@DATA", "valve"]):
                    print(f"RX: {line}")
        time.sleep(0.05)
    
    if not any("@ACK" in r or "@INFO" in r for r in responses):
        print("⚠ No ACK received")
    
    return responses

def main():
    print("=" * 60)
    print("Set Valve Target")
    print(f"Valve EUI64: {VALVE_EUI64}")
    print("=" * 60)
    
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=2)
        print(f"✓ Connected to {COM_PORT}")
        time.sleep(0.5)
        ser.reset_input_buffer()
        
        # Step 1: Get current info
        send_cmd(ser, '@CMD {"id":1,"op":"info"}\n', "Get current info", wait=1.5)
        
        # Step 2: Try setting valve_path to binding first
        send_cmd(ser, '@CMD {"id":2,"op":"valve_path_set","value":"binding"}\n', "Set valve path to BINDING", wait=1.0)
        
        # Step 3: Try valve_pair with common node IDs (0x0001, 0x0002)
        # Zigbee short addresses are typically assigned incrementally
        for node_id in ["0x0001", "0x0002", "0x0003", "0x0054"]:
            cmd = f'@CMD {{"id":10,"op":"valve_pair","eui64":"{VALVE_EUI64}","node_id":"{node_id}"}}\n'
            responses = send_cmd(ser, cmd, f"Try valve_pair with node_id={node_id}", wait=1.0)
            
            # Check if successful
            for r in responses:
                if "@ACK" in r and '"ok":true' in r:
                    print(f"✓ SUCCESS with node_id={node_id}!")
                    break
        
        # Step 4: Get info again to see if valve is now known
        send_cmd(ser, '@CMD {"id":20,"op":"info"}\n', "Check valve status", wait=1.5)
        
        # Step 5: Try valve command
        print("\n" + "=" * 60)
        print("Testing Valve Commands")
        print("=" * 60)
        
        send_cmd(ser, '@CMD {"id":30,"op":"valve_set","value":"open"}\n', "Valve OPEN", wait=2.0)
        time.sleep(1)
        send_cmd(ser, '@CMD {"id":31,"op":"valve_set","value":"closed"}\n', "Valve CLOSE", wait=2.0)
        
        # Final info
        send_cmd(ser, '@CMD {"id":99,"op":"info"}\n', "Final status", wait=1.5)
        
        ser.close()
        print("\n✓ Done")
        
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    main()
