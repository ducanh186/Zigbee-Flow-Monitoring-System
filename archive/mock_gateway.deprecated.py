"""
⚠️ DEPRECATED - DO NOT USE ⚠️

This file has been replaced by the new gateway.service module.

OLD (deprecated):
    python mock_gateway.py

NEW (use this instead):
    python -m gateway.service --fake-uart

The new service.py provides:
- Better UART protocol handling
- Rules engine (lock, cooldown, dedupe)
- ACK timeout handling
- Proper state management
- Compatible with CONTRACT.md

Kept for reference only.
"""

raise DeprecationWarning(
    "\n\n"
    "========================================\n"
    "⚠️  mock_gateway.py is DEPRECATED  ⚠️\n"
    "========================================\n"
    "\n"
    "Use instead:\n"
    "  python -m gateway.service --fake-uart\n"
    "\n"
    "See README_FOR_UI_DEV.md for details.\n"
)

SITE = "lab1"
BASE = f"wfms/{SITE}"
TOPIC_STATE = f"{BASE}/state"
TOPIC_TELEM = f"{BASE}/telemetry"
TOPIC_CMD_V = f"{BASE}/cmd/valve"
TOPIC_ACK   = f"{BASE}/ack"
TOPIC_GW    = f"{BASE}/status/gateway"

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883

state = {"flow": 0, "battery": 90, "valve": "OFF", "updatedAt": int(time.time())}
lock = False  # mock: có thể bật tay nếu muốn test

def now():
    return int(time.time())

def publish_loop(client: mqtt.Client):
    while True:
        # fake telemetry
        state["flow"] = (state["flow"] + 5) % 100
        state["battery"] = max(0, state["battery"] - 1 if random.random() < 0.05 else state["battery"])
        state["updatedAt"] = now()

        client.publish(TOPIC_TELEM, json.dumps(state), qos=0)
        client.publish(TOPIC_STATE, json.dumps(state), qos=0, retain=True)
        time.sleep(1)

def on_connect(client, userdata, flags, rc):
    print(f"✓ Connected to MQTT broker (rc={rc})")
    client.publish(TOPIC_GW, json.dumps({"up": True, "ts": now()}), retain=True)
    client.subscribe(TOPIC_CMD_V, qos=0)
    print(f"✓ Subscribed to {TOPIC_CMD_V}")

def on_message(client, userdata, msg):
    global lock
    try:
        cmd = json.loads(msg.payload.decode())
    except Exception:
        return

    cid = cmd.get("cid", "?")
    value = cmd.get("value")

    if lock:
        ack = {"cid": cid, "ok": False, "reason": "locked", "ts": now()}
        client.publish(TOPIC_ACK, json.dumps(ack), qos=0)
        return

    if value not in ("ON", "OFF"):
        ack = {"cid": cid, "ok": False, "reason": "invalid_value", "ts": now()}
        client.publish(TOPIC_ACK, json.dumps(ack), qos=0)
        return

    # apply
    state["valve"] = value
    state["updatedAt"] = now()

    ack = {"cid": cid, "ok": True, "reason": "", "ts": now()}
    client.publish(TOPIC_ACK, json.dumps(ack), qos=0)
    client.publish(TOPIC_STATE, json.dumps(state), qos=0, retain=True)

def main():
    print("=== Mock WFMS Gateway ===")
    print(f"MQTT: {MQTT_HOST}:{MQTT_PORT}")
    print(f"Site: {SITE}")
    print("Attempting to connect to MQTT broker...")
    
    client = mqtt.Client()
    client.will_set(TOPIC_GW, json.dumps({"up": False, "ts": now()}), retain=True)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    except ConnectionRefusedError:
        print("\n❌ ERROR: Cannot connect to MQTT broker!")
        print(f"\nPlease ensure MQTT broker is running on {MQTT_HOST}:{MQTT_PORT}")
        print("\nTo install Mosquitto MQTT broker:")
        print("  Windows: Download from https://mosquitto.org/download/")
        print("           Or: winget install EclipseFoundation.Mosquitto")
        print("  Linux:   sudo apt install mosquitto mosquitto-clients")
        print("  macOS:   brew install mosquitto")
        print("\nAfter installation, start the broker:")
        print("  Windows: mosquitto -v")
        print("  Linux:   sudo systemctl start mosquitto")
        print("  macOS:   brew services start mosquitto")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)

    t = threading.Thread(target=publish_loop, args=(client,), daemon=True)
    t.start()

    print("\n✓ Mock gateway running. Press Ctrl+C to stop.\n")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\n✓ Shutting down...")
        client.disconnect()

if __name__ == "__main__":
    main()
