import json
import time
import threading
from queue import Queue, Empty

import serial
import paho.mqtt.client as mqtt

# ======================
# CONFIG
# ======================
SERIAL_PORT = "COM10"
BAUDRATE = 115200

BROKER_HOST = "YOUR_BROKER_HOST"
BROKER_PORT = 8883  # 8883 for TLS, 1883 for non-TLS (not recommended on Internet)
BROKER_USER = "YOUR_USER"
BROKER_PASS = "YOUR_PASS"

BASE = "wfms/pca"  # change pca if you want multiple gateways
TOPIC_INFO = f"{BASE}/info"
TOPIC_DATA = f"{BASE}/data"
TOPIC_LOG  = f"{BASE}/log"
TOPIC_ACK  = f"{BASE}/ack"
TOPIC_CMD  = f"{BASE}/cmd"
TOPIC_STATUS = f"{BASE}/status"

# ======================
# SERIAL
# ======================
ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.2)
ser_lock = threading.Lock()

def serial_write_line(line: str) -> None:
    if not line.endswith("\n"):
        line += "\n"
    with ser_lock:
        ser.write(line.encode("utf-8"))

def parse_prefixed_json(line: str):
    """Return (prefix, obj) or (None, None)"""
    line = line.strip()
    for prefix in ("@INFO", "@DATA", "@LOG", "@ACK"):
        if line.startswith(prefix + " "):
            payload = line[len(prefix) + 1:].strip()
            try:
                return prefix, json.loads(payload)
            except Exception:
                return prefix, None
    return None, None

# ======================
# MQTT
# ======================
def mqtt_publish_json(client: mqtt.Client, topic: str, obj: dict, qos=1, retain=False):
    obj = dict(obj)
    obj["ts"] = int(time.time())
    client.publish(topic, json.dumps(obj, separators=(",", ":")), qos=qos, retain=retain)

def on_connect(client, userdata, flags, rc):
    print("MQTT connected rc=", rc)
    client.subscribe(TOPIC_CMD, qos=1)
    # Online status (retain)
    mqtt_publish_json(client, TOPIC_STATUS, {"online": True}, qos=1, retain=True)

def on_disconnect(client, userdata, rc):
    print("MQTT disconnected rc=", rc)

def on_message(client, userdata, msg):
    if msg.topic != TOPIC_CMD:
        return
    try:
        cmd = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        return

    # Ensure id exists (your UART protocol expects id for @ACK)
    if "id" not in cmd:
        cmd["id"] = int(time.time())  # fallback

    # Forward to coordinator via UART
    serial_write_line("@CMD " + json.dumps(cmd))

    # Optional immediate ack "sent_to_uart" (real ack comes from coordinator @ACK)
    mqtt_publish_json(client, TOPIC_ACK, {"id": cmd["id"], "ok": True, "msg": "sent_to_uart"}, qos=1, retain=False)

def uart_reader_loop(client: mqtt.Client):
    while True:
        raw = ser.readline().decode("utf-8", errors="ignore").strip()
        if not raw:
            continue

        prefix, obj = parse_prefixed_json(raw)
        if prefix is None:
            continue

        if obj is None:
            mqtt_publish_json(client, TOPIC_LOG, {"tag":"UART","event":"json_parse_fail","raw":raw}, qos=0, retain=False)
            continue

        if prefix == "@INFO":
            mqtt_publish_json(client, TOPIC_INFO, obj, qos=1, retain=True)
        elif prefix == "@DATA":
            mqtt_publish_json(client, TOPIC_DATA, obj, qos=1, retain=True)
        elif prefix == "@LOG":
            mqtt_publish_json(client, TOPIC_LOG, obj, qos=0, retain=False)
        elif prefix == "@ACK":
            mqtt_publish_json(client, TOPIC_ACK, obj, qos=1, retain=False)

def main():
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    client.username_pw_set(BROKER_USER, BROKER_PASS)

    # TLS: most cloud brokers require TLS
    client.tls_set()

    # LWT: if gateway dies, broker publishes offline
    client.will_set(TOPIC_STATUS, json.dumps({"online": False, "ts": int(time.time())}), qos=1, retain=True)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)

    t = threading.Thread(target=uart_reader_loop, args=(client,), daemon=True)
    t.start()

    client.loop_forever()

if __name__ == "__main__":
    main()
