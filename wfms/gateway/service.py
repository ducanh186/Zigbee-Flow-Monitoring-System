"""
WFMS Gateway Service

Main entry point for the Gateway service that bridges UART ⇄ MQTT.
Supports two modes:
- Real UART: Connect to actual Zigbee Coordinator via serial port
- Fake UART: Simulated UART for UI development without hardware

Usage:
    python -m gateway.service                    # Real UART mode
    python -m gateway.service --fake-uart       # Fake UART mode
    python -m gateway.service --fake-uart --drop-ack-prob 0.2  # With 20% ACK drop
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass

import paho.mqtt.client as mqtt

# Add parent to path for imports when running as module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.proto import (
    parse_uart_line, make_cmd_line, now_ts, validate_cmd_payload, 
    translate_coordinator_ack, translate_coordinator_data,
    VALVE_COORD_TO_MQTT
)
from common.contract import (
    TOPIC_STATE, TOPIC_TELEMETRY, TOPIC_CMD_VALVE, TOPIC_ACK, 
    TOPIC_GATEWAY_STATUS, VALVE_ON, VALVE_OFF, update_site
)
from gateway.config import load_config, Config
from gateway.uart import UartBase, RealUart, FakeUart
from gateway.rules import Rules, RulesConfig
from gateway.runtime import RuntimeState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("gateway")


@dataclass
class StateCache:
    """Cached state from UART data (Coordinator format)."""
    flow: float = 0.0
    battery: int = 100
    valve: str = "OFF"  # MQTT format (ON/OFF)
    mode: str = "auto"  # auto/manual
    valve_path: str = "auto"  # auto/direct/binding
    valve_known: bool = False
    valve_node_id: str = ""
    tx_pending: bool = False
    updated_at: int = 0
    
    def to_dict(self) -> dict:
        return {
            "flow": self.flow,
            "battery": self.battery,
            "valve": self.valve,
            "mode": self.mode,
            "valvePath": self.valve_path,
            "valveKnown": self.valve_known,
            "valveNodeId": self.valve_node_id,
            "txPending": self.tx_pending,
            "updatedAt": self.updated_at
        }
    
    def update_from_data(self, data: dict) -> None:
        """
        Update state from @DATA payload.
        
        Coordinator DATA format:
        {"flow":150,"valve":"open","battery":85,"mode":"auto",...}
        """
        if "flow" in data:
            self.flow = data["flow"]
        if "battery" in data:
            self.battery = data["battery"]
        if "valve" in data:
            # Translate Coordinator format (open/closed) to MQTT (ON/OFF)
            valve_state = data["valve"].lower()
            self.valve = VALVE_COORD_TO_MQTT.get(valve_state, "OFF")
        if "mode" in data:
            self.mode = data["mode"]
        if "valve_path" in data:
            self.valve_path = data["valve_path"]
        if "valve_known" in data:
            self.valve_known = data["valve_known"]
        if "valve_node_id" in data:
            self.valve_node_id = data["valve_node_id"]
        if "tx_pending" in data:
            self.tx_pending = data["tx_pending"]
        self.updated_at = now_ts()


@dataclass
class CoordinatorInfo:
    """Cached info from @INFO message (heartbeat)."""
    node_id: str = ""
    eui64: str = ""
    pan_id: str = ""
    channel: int = 0
    tx_power: int = 0
    net_state: int = 0
    uart_gateway: bool = False
    mode: str = "auto"
    valve_path: str = "auto"
    valve_known: bool = False
    valve_eui64: str = ""
    valve_node_id: str = ""
    bind_index: int = 0
    uptime: int = 0
    updated_at: int = 0
    
    def to_dict(self) -> dict:
        return {
            "nodeId": self.node_id,
            "eui64": self.eui64,
            "panId": self.pan_id,
            "channel": self.channel,
            "txPower": self.tx_power,
            "netState": self.net_state,
            "uartGateway": self.uart_gateway,
            "mode": self.mode,
            "valvePath": self.valve_path,
            "valveKnown": self.valve_known,
            "valveEui64": self.valve_eui64,
            "valveNodeId": self.valve_node_id,
            "bindIndex": self.bind_index,
            "uptime": self.uptime,
            "updatedAt": self.updated_at
        }
    
    def update_from_info(self, info: dict) -> None:
        """Update from @INFO payload."""
        if "node_id" in info:
            self.node_id = info["node_id"]
        if "eui64" in info:
            self.eui64 = info["eui64"]
        if "pan_id" in info:
            self.pan_id = info["pan_id"]
        if "ch" in info:
            self.channel = info["ch"]
        if "tx_power" in info:
            self.tx_power = info["tx_power"]
        if "net_state" in info:
            self.net_state = info["net_state"]
        if "uart_gateway" in info:
            self.uart_gateway = info["uart_gateway"]
        if "mode" in info:
            self.mode = info["mode"]
        if "valve_path" in info:
            self.valve_path = info["valve_path"]
        if "valve_known" in info:
            self.valve_known = info["valve_known"]
        if "valve_eui64" in info:
            self.valve_eui64 = info["valve_eui64"]
        if "valve_node_id" in info:
            self.valve_node_id = info["valve_node_id"]
        if "bind_index" in info:
            self.bind_index = info["bind_index"]
        if "uptime" in info:
            self.uptime = info["uptime"]
        self.updated_at = now_ts()


class AckRouter:
    """
    Routes ACK responses to waiting command handlers.
    Uses threading Events for synchronization.
    """
    
    def __init__(self, default_timeout: float = 3.0):
        self.default_timeout = default_timeout
        self._pending: Dict[str, dict] = {}  # cid -> {"event": Event, "result": dict}
        self._lock = threading.Lock()
    
    def wait_for_ack(self, cid: str, timeout: Optional[float] = None) -> Optional[dict]:
        """
        Wait for an ACK with the given CID.
        
        Args:
            cid: Command ID to wait for
            timeout: Max seconds to wait (default: default_timeout)
        
        Returns:
            ACK payload dict if received, None on timeout
        """
        timeout = timeout or self.default_timeout
        event = threading.Event()
        
        with self._lock:
            self._pending[cid] = {"event": event, "result": None}
        
        # Wait for ACK
        received = event.wait(timeout=timeout)
        
        with self._lock:
            entry = self._pending.pop(cid, None)
        
        if received and entry:
            return entry.get("result")
        return None
    
    def resolve(self, cid: str, ack_payload: dict) -> bool:
        """
        Resolve a pending ACK wait.
        
        Args:
            cid: Command ID
            ack_payload: ACK payload from UART
        
        Returns:
            True if there was a waiter for this CID
        """
        with self._lock:
            if cid in self._pending:
                self._pending[cid]["result"] = ack_payload
                self._pending[cid]["event"].set()
                return True
        return False


class GatewayService:
    """
    Main Gateway Service class.
    Bridges UART (real or fake) to MQTT.
    """
    
    def __init__(self, config: Config, uart: UartBase, runtime: Optional[RuntimeState] = None):
        self.config = config
        self.uart = uart
        self.runtime = runtime or RuntimeState()
        
        # State
        self.state = StateCache()
        self.coordinator_info = CoordinatorInfo()  # @INFO cache
        self.ack_router = AckRouter(default_timeout=config.ack_timeout_s)
        
        # Rules engine
        rules_config = RulesConfig(
            lock=config.is_locked,
            cooldown_user_s=config.rule_cooldown_user_s,
            cooldown_global_s=config.rule_cooldown_global_s,
            dedupe_ttl_s=config.rule_dedupe_ttl_s
        )
        self.rules = Rules(rules_config)
        
        # MQTT client
        self.mqtt_client: Optional[mqtt.Client] = None
        
        # Control
        self._running = False
        self._uart_thread: Optional[threading.Thread] = None
        self._api_thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """Start the gateway service."""
        logger.info("=" * 50)
        logger.info("WFMS Gateway Service Starting")
        logger.info("=" * 50)
        logger.info(f"Site: {self.config.site}")
        logger.info(f"MQTT: {self.config.mqtt_host}:{self.config.mqtt_port}")
        logger.info(f"UART: {self.config.uart_port} @ {self.config.uart_baud}")
        logger.info(f"Admin API: http://{self.config.api_host}:{self.config.api_port}")
        logger.info(f"Lock: {'ENABLED' if self.config.is_locked else 'DISABLED'}")
        logger.info("=" * 50)
        
        self._running = True
        
        # Start UART
        self.uart.start()
        self.runtime.set_uart_connected(True)
        
        # Setup MQTT
        self._setup_mqtt()
        
        # Start Admin API in background thread
        self._start_admin_api()
        
        # Start UART reader thread
        self._uart_thread = threading.Thread(
            target=self._uart_reader_loop,
            daemon=True,
            name="uart-reader"
        )
        self._uart_thread.start()
        
        # Log to runtime
        self.runtime.add_log("INFO", f"Gateway started (site={self.config.site})")
        
        # Start MQTT loop (blocking)
        try:
            self.mqtt_client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the gateway service."""
        logger.info("Gateway shutting down...")
        self._running = False
        
        # Log to runtime
        self.runtime.add_log("INFO", "Gateway shutting down")
        
        # Publish offline status
        if self.mqtt_client and self.mqtt_client.is_connected():
            offline_status = json.dumps({"up": False, "ts": now_ts()})
            self.mqtt_client.publish(TOPIC_GATEWAY_STATUS, offline_status, qos=1, retain=True)
            self.mqtt_client.disconnect()
        
        # Update runtime state
        self.runtime.set_mqtt_connected(False)
        self.runtime.set_uart_connected(False)
        
        # Stop UART
        self.uart.stop()
        
        logger.info("Gateway stopped")
    
    def _start_admin_api(self) -> None:
        """Start Admin API server in background thread."""
        try:
            from gateway.admin_api import make_app, run_api_server
            
            app = make_app(
                runtime=self.runtime,
                rules=self.rules,
                config=self.config,
                api_token=self.config.api_token if self.config.api_auth_enabled else None
            )
            
            self._api_thread = threading.Thread(
                target=run_api_server,
                kwargs={
                    "app": app,
                    "host": self.config.api_host,
                    "port": self.config.api_port,
                    "log_level": "warning"
                },
                daemon=True,
                name="admin-api"
            )
            self._api_thread.start()
            logger.info(f"✓ Admin API started on http://{self.config.api_host}:{self.config.api_port}")
            self.runtime.add_log("INFO", f"Admin API started on port {self.config.api_port}")
        except Exception as e:
            logger.error(f"Failed to start Admin API: {e}")
            self.runtime.add_log("ERROR", f"Admin API failed: {e}")
    
    def _setup_mqtt(self) -> None:
        """Setup MQTT client with LWT and callbacks."""
        self.mqtt_client = mqtt.Client()
        
        # Set Last Will and Testament (LWT)
        lwt_payload = json.dumps({"up": False, "ts": now_ts()})
        self.mqtt_client.will_set(
            TOPIC_GATEWAY_STATUS,
            lwt_payload,
            qos=1,
            retain=True
        )
        
        # Set credentials if configured
        if self.config.mqtt_auth_enabled:
            self.mqtt_client.username_pw_set(
                self.config.mqtt_user,
                self.config.mqtt_pass
            )
        
        # Set callbacks
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self.mqtt_client.on_message = self._on_mqtt_message
        
        # Connect
        logger.info(f"Connecting to MQTT broker {self.config.mqtt_host}:{self.config.mqtt_port}...")
        try:
            self.mqtt_client.connect(
                self.config.mqtt_host,
                self.config.mqtt_port,
                keepalive=30
            )
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            raise
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connect callback."""
        if rc == 0:
            logger.info("✓ MQTT connected")
            self.runtime.set_mqtt_connected(True)
            self.runtime.add_log("INFO", "MQTT connected")
            
            # Publish online status (retained)
            online_status = json.dumps({"up": True, "ts": now_ts()})
            client.publish(TOPIC_GATEWAY_STATUS, online_status, qos=1, retain=True)
            
            # Subscribe to command topic
            client.subscribe(TOPIC_CMD_VALVE, qos=1)
            logger.info(f"✓ Subscribed to {TOPIC_CMD_VALVE}")
        else:
            logger.error(f"MQTT connect failed with code {rc}")
            self.runtime.set_mqtt_connected(False)
            self.runtime.add_log("ERROR", f"MQTT connect failed (rc={rc})")
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnect callback."""
        self.runtime.set_mqtt_connected(False)
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc}), will auto-reconnect")
            self.runtime.add_log("WARNING", f"MQTT disconnected (rc={rc})")
        else:
            logger.info("MQTT disconnected")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT command messages."""
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Invalid JSON in command: {e}")
            return
        
        logger.info(f"Received command: {payload}")
        
        # Increment command counter
        self.runtime.inc_cmd()
        
        # Validate payload
        valid, reason = validate_cmd_payload(payload)
        if not valid:
            self._publish_ack(payload.get("cid", "unknown"), False, reason)
            return
        
        cid = payload["cid"]
        value = payload["value"]
        user = payload.get("by", "anonymous")
        
        # Apply rules
        allowed, rule_reason = self.rules.check_and_mark(cid, user)
        if not allowed:
            logger.warning(f"Command rejected by rules: cid={cid}, reason={rule_reason}")
            self._publish_ack(cid, False, rule_reason)
            return
        
        # Send command to UART
        cmd_line = make_cmd_line(payload)
        logger.info(f"TX >>> {cmd_line.strip()}")  # Mức 1: Log TX rõ ràng
        
        if not self.uart.write_line(cmd_line):
            logger.error(f"TX FAILED: uart.write_line() returned False")
            self._publish_ack(cid, False, "uart_write_failed")
            return
        
        logger.info(f"TX OK: Waiting ACK for cid={cid} (timeout={self.config.ack_timeout_s}s)")
        
        # Wait for ACK from UART
        ack = self.ack_router.wait_for_ack(cid, timeout=self.config.ack_timeout_s)
        
        if ack is None:
            logger.warning(f"ACK timeout for cid={cid}")
            self._publish_ack(cid, False, "timeout")
            return
        
        # Process ACK
        ok = ack.get("ok", False)
        ack_reason = ack.get("reason", "")
        
        if ok:
            # Update state cache with new valve state
            self.state.valve = value
            self.state.updated_at = now_ts()
            self._publish_state()
        
        self._publish_ack(cid, ok, ack_reason)
    
    def _uart_reader_loop(self) -> None:
        """Background thread reading from UART."""
        logger.info("UART reader thread started")
        
        while self._running:
            line = self.uart.read_line(timeout=1.0)
            if line is None:
                continue
            
            msg_type, payload = parse_uart_line(line)
            
            if msg_type == "DATA":
                self._handle_uart_data(payload)
            elif msg_type == "ACK":
                self._handle_uart_ack(payload)
            elif msg_type == "INFO":
                self._handle_uart_info(payload)
            elif msg_type == "LOG":
                self._handle_uart_log(payload)
            elif msg_type == "ERR":
                error = payload.get("error", "")
                raw = payload.get("raw", "")
                
                # Check if this is a fragment (no prefix but looks like JSON)
                if error == "unknown_prefix" and (raw.startswith('{') or raw.endswith('}')):
                    logger.warning(f"⚠ UART FRAGMENT detected: '{raw[:50]}...' (possible buffer issue)")
                elif error == "empty_line":
                    # Empty lines are common noise, downgrade to debug
                    logger.debug("UART: empty line")
                else:
                    logger.warning(f"UART parse error: {payload}")
        
        logger.info("UART reader thread stopped")
    
    def _handle_uart_data(self, data: dict) -> None:
        """
        Handle @DATA from UART (Coordinator format).
        
        Coordinator DATA: {"flow":150,"valve":"open","battery":85,"mode":"auto",...}
        """
        logger.debug(f"RX @DATA: {data}")
        
        # Update state cache (handles valve translation: open->ON, closed->OFF)
        self.state.update_from_data(data)
        
        # Also update mode in coordinator_info if present
        if "mode" in data:
            self.coordinator_info.mode = data["mode"]
        
        # Increment telemetry counter
        self.runtime.inc_telemetry()
        
        # Publish telemetry (non-retained)
        telemetry = {
            "flow": self.state.flow,
            "battery": self.state.battery,
            "valve": self.state.valve,  # Already translated to ON/OFF
            "mode": self.state.mode,
            "ts": now_ts()
        }
        self.mqtt_client.publish(
            TOPIC_TELEMETRY,
            json.dumps(telemetry),
            qos=0,
            retain=False
        )
        
        # Publish state (retained)
        self._publish_state()
    
    def _handle_uart_info(self, info: dict) -> None:
        """
        Handle @INFO from UART (Coordinator heartbeat).
        
        Coordinator INFO: {"node_id":"0x0000","eui64":"...","pan_id":"0xBEEF","ch":11,...}
        """
        logger.debug(f"RX @INFO: {info}")
        
        # Update coordinator info cache
        self.coordinator_info.update_from_info(info)
        
        # Sync mode to state cache
        if "mode" in info:
            self.state.mode = info["mode"]
        if "valve_path" in info:
            self.state.valve_path = info["valve_path"]
        if "valve_known" in info:
            self.state.valve_known = info["valve_known"]
        
        # Log important info on first receive or significant changes
        logger.info(f"Coordinator: node={info.get('node_id', '?')}, "
                   f"pan={info.get('pan_id', '?')}, ch={info.get('ch', '?')}, "
                   f"mode={info.get('mode', '?')}, uptime={info.get('uptime', '?')}s")
    
    def _handle_uart_log(self, log: dict) -> None:
        """
        Handle @LOG from UART (Coordinator event log).
        
        Coordinator LOG: {"tag":"NET","event":"formed","pan_id":"0xBEEF",...}
        """
        tag = log.get("tag", "???")
        event = log.get("event", "")
        logger.info(f"[Coordinator {tag}] {event}: {log}")
        
        # Add to runtime log
        self.runtime.add_log(f"COORD_{tag}", f"{event}: {json.dumps(log)}")
    
    def _handle_uart_ack(self, ack: dict) -> None:
        """
        Handle @ACK from UART (Coordinator format).
        
        Coordinator ACK: {"id":123,"ok":true,"msg":"valve set","valve":"open"}
        Translated to:   {"cid":"xxx","ok":true,"reason":"valve set","valve":"open"}
        """
        logger.debug(f"RX @ACK: {ack}")
        
        # Check if this is Coordinator format (has "id" field) or MQTT format (has "cid" field)
        if "id" in ack and "cid" not in ack:
            # Coordinator format - translate
            mqtt_ack = translate_coordinator_ack(ack)
            cid = mqtt_ack.get("cid")
            logger.info(f"ACK from Coordinator: id={ack.get('id')} -> cid={cid}, "
                       f"ok={ack.get('ok')}, msg={ack.get('msg', '')}")
        else:
            # Already MQTT format (from FakeUart)
            mqtt_ack = ack
            cid = ack.get("cid")
        
        if cid:
            resolved = self.ack_router.resolve(cid, mqtt_ack)
            if not resolved:
                logger.debug(f"Received ACK for unknown cid={cid}")
    
    def _publish_state(self) -> None:
        """Publish current state (retained)."""
        self.mqtt_client.publish(
            TOPIC_STATE,
            json.dumps(self.state.to_dict()),
            qos=1,
            retain=True
        )
    
    def _publish_ack(self, cid: str, ok: bool, reason: str) -> None:
        """Publish command acknowledgment."""
        # Increment ACK counter
        self.runtime.inc_ack(ok)
        
        ack = {
            "cid": cid,
            "ok": ok,
            "reason": reason,
            "ts": now_ts()
        }
        self.mqtt_client.publish(
            TOPIC_ACK,
            json.dumps(ack),
            qos=1,
            retain=False
        )
        logger.info(f"Published ACK: cid={cid}, ok={ok}, reason={reason}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="WFMS Gateway Service - Bridge UART to MQTT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m gateway.service                         # Real UART from .env
  python -m gateway.service --fake-uart            # Fake UART mode
  python -m gateway.service --fake-uart --drop-ack-prob 0.3  # With 30% ACK drop
  python -m gateway.service --uart COM10 --baud 115200       # Override port/baud
        """
    )
    
    parser.add_argument(
        "--fake-uart",
        action="store_true",
        help="Use fake UART emulation (no hardware needed)"
    )
    
    parser.add_argument(
        "--drop-ack-prob",
        type=float,
        default=0.0,
        help="Probability of dropping ACK in fake mode (0.0-1.0, default: 0.0)"
    )
    
    parser.add_argument(
        "--uart",
        type=str,
        help="Override UART port (e.g., COM10 or /dev/ttyUSB0)"
    )
    
    parser.add_argument(
        "--baud",
        type=int,
        help="Override UART baud rate"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Set log level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    
    # Load config
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)
    
    # Override config from args
    if args.uart:
        config.uart_port = args.uart
    if args.baud:
        config.uart_baud = args.baud
    
    # Update contract topics with site from config
    update_site(config.site)
    
    # Re-import topics after update
    from common.contract import (
        TOPIC_STATE, TOPIC_TELEMETRY, TOPIC_CMD_VALVE, 
        TOPIC_ACK, TOPIC_GATEWAY_STATUS
    )
    
    # Create UART instance
    if args.fake_uart:
        logger.info("=" * 50)
        logger.info("   FAKE UART MODE (for UI development)")
        logger.info(f"   Drop ACK probability: {args.drop_ack_prob}")
        logger.info("=" * 50)
        uart = FakeUart(
            data_interval=1.0,
            drop_ack_prob=args.drop_ack_prob
        )
    else:
        logger.info("Real UART mode")
        uart = RealUart(
            port=config.uart_port,
            baud=config.uart_baud
        )
    
    # Create and start service
    service = GatewayService(config, uart)
    
    try:
        service.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Service error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
