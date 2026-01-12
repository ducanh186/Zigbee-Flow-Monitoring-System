"""
Configure Coordinator to control Valve Node 0x1D34
"""

import serial
import time

COM_PORT = "COM13"
BAUD_RATE = 115200
VALVE_EUI64 = "0000000000000054"
VALVE_NODE_ID = "0x1D34"

def send_cmd_slow(ser, cmd, desc, wait=1.5):
    """Send command with longer delays to avoid UART corruption"""
    print(f"\n--- {desc} ---")
    print(f"TX: {cmd.strip()}")
    
    # Clear buffer
    ser.reset_input_buffer()
    
    # Add delay before sending
    time.sleep(0.5)
    
    # Send command
    ser.write(cmd.encode())
    ser.flush()
    
    # Wait for response
    time.sleep(wait)
    
    responses = []
    while ser.in_waiting:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if line:
            responses.append(line)
            # Filter important lines
            if any(x in line for x in ["@ACK", "@INFO", "valve"]):
                print(f"RX: {line}")
    
    return responses

def main():
    print("=" * 70)
    print(f"Configure Coordinator for Valve Node {VALVE_NODE_ID}")
    print("=" * 70)
    
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=2)
        print(f"✓ Connected to {COM_PORT}")
        time.sleep(1)
        
        # Step 1: Set mode to MANUAL
        send_cmd_slow(ser, '@CMD {"id":1,"op":"mode_set","value":"manual"}\n', 
                     "Set mode to MANUAL", wait=1.0)
        
        # Step 2: Set valve path to BINDING (recommended)
        send_cmd_slow(ser, '@CMD {"id":2,"op":"valve_path_set","value":"binding"}\n',
                     "Set valve path to BINDING", wait=1.0)
        
        # Step 3: Pair valve with EUI64 and Node ID
        cmd = f'@CMD {{"id":3,"op":"valve_pair","eui64":"{VALVE_EUI64}","node_id":"{VALVE_NODE_ID}","bind_index":0}}\n'
        send_cmd_slow(ser, cmd, f"Pair valve {VALVE_NODE_ID}", wait=2.0)
        
        # Step 4: Get info to verify
        send_cmd_slow(ser, '@CMD {"id":4,"op":"info"}\n',
                     "Verify configuration", wait=2.0)
        
        # Step 5: Test valve OPEN
        print("\n" + "=" * 70)
        print("TESTING VALVE CONTROL")
        print("=" * 70)
        
        send_cmd_slow(ser, '@CMD {"id":10,"op":"valve_set","value":"open"}\n',
                     "🔓 Valve OPEN", wait=2.5)
        
        time.sleep(2)
        
        # Step 6: Test valve CLOSE
        send_cmd_slow(ser, '@CMD {"id":11,"op":"valve_set","value":"closed"}\n',
                     "🔒 Valve CLOSE", wait=2.5)
        
        # Final status
        send_cmd_slow(ser, '@CMD {"id":99,"op":"info"}\n',
                     "Final status", wait=2.0)
        
        ser.close()
        print("\n✅ Configuration complete!")
        print(f"Valve {VALVE_NODE_ID} is now configured.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
