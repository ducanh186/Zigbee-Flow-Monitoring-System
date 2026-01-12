"""
Simple MQTT Monitor for Machine B (no hardware)
Subscribe to MQTT broker and display telemetry data
"""

import json
import paho.mqtt.client as mqtt
from datetime import datetime

# Configuration
MQTT_BROKER = "26.172.222.181"  # Machine A IP
MQTT_PORT = 1883
MQTT_TOPIC = "wfms/lab1/#"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        print(f"📡 Subscribed to: {MQTT_TOPIC}")
        print("=" * 80)
    else:
        print(f"❌ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    topic = msg.topic
    
    try:
        payload = json.loads(msg.payload.decode())
        
        # Format display based on topic
        if "telemetry" in topic:
            flow = payload.get("flow", "N/A")
            battery = payload.get("battery", "N/A")
            valve = payload.get("valve", "N/A")
            mode = payload.get("mode", "N/A")
            print(f"[{timestamp}] 📊 TELEMETRY | Flow: {flow:>3} | Battery: {battery:>3}% | Valve: {valve:<4} | Mode: {mode}")
        
        elif "state" in topic:
            print(f"[{timestamp}] 🔄 STATE     | {json.dumps(payload, indent=None)}")
        
        elif "status/gateway" in topic:
            print(f"[{timestamp}] 🌐 GATEWAY   | {json.dumps(payload)}")
        
        elif "cmd/valve" in topic:
            print(f"[{timestamp}] 🎮 COMMAND   | {json.dumps(payload)}")
        
        elif "ack/valve" in topic:
            print(f"[{timestamp}] ✔️  ACK       | {json.dumps(payload)}")
        
        else:
            print(f"[{timestamp}] 📨 {topic} | {msg.payload.decode()}")
            
    except json.JSONDecodeError:
        print(f"[{timestamp}] 📨 {topic} | {msg.payload.decode()}")
    except Exception as e:
        print(f"[{timestamp}] ⚠️  ERROR: {e}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"\n⚠️  Disconnected unexpectedly (code {rc})")
    else:
        print("\n👋 Disconnected gracefully")

def main():
    print("=" * 80)
    print("🔍 WFMS MQTT Monitor - Machine B (Remote Viewer)")
    print("=" * 80)
    print(f"Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Topic:  {MQTT_TOPIC}")
    print("=" * 80)
    
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    
    try:
        print(f"🔌 Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user (Ctrl+C)")
        client.disconnect()
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
