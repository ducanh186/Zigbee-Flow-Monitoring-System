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

from common.proto import parse_uart_line, make_cmd_line, now_ts, validate_cmd_payload
from common.contract import (
    TOPIC_STATE, TOPIC_TELEMETRY, TOPIC_CMD_VALVE, TOPIC_ACK, 
    TOPIC_GATEWAY_STATUS, VALVE_ON, VALVE_OFF, update_site
)
from gateway.config import load_config, Config
from gateway.uart import UartBase, RealUart, FakeUart
from gateway.rules import Rules, RulesConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("gateway")


@dataclass
class StateCache:
    """Cached state from UART data."""
    flow: float = 0.0
    battery: int = 100
    valve: str = "OFF"
    updated_at: int = 0
    
    def to_dict(self) -> dict:
        return {
            "flow": self.flow,
            "battery": self.battery,
            "valve": self.valve,
            "updatedAt": self.updated_at
        }
    
    def update_from_data(self, data: dict) -> None:
        """Update state from @DATA payload."""
        if "flow" in data:
            self.flow = data["flow"]
        if "battery" in data:
            self.battery = data["battery"]
        if "valve" in data:
            self.valve = data["valve"]
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
    
    def __init__(self, config: Config, uart: UartBase):
        self.config = config
        self.uart = uart
        
        # State
        self.state = StateCache()
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
    
    def start(self) -> None:
        """Start the gateway service."""
        logger.info("=" * 50)
        logger.info("WFMS Gateway Service Starting")
        logger.info("=" * 50)
        logger.info(f"Site: {self.config.site}")
        logger.info(f"MQTT: {self.config.mqtt_host}:{self.config.mqtt_port}")
        logger.info(f"UART: {self.config.uart_port} @ {self.config.uart_baud}")
        logger.info(f"Lock: {'ENABLED' if self.config.is_locked else 'DISABLED'}")
        logger.info("=" * 50)
        
        self._running = True
        
        # Start UART
        self.uart.start()
        
        # Setup MQTT
        self._setup_mqtt()
        
        # Start UART reader thread
        self._uart_thread = threading.Thread(
            target=self._uart_reader_loop,
            daemon=True,
            name="uart-reader"
        )
        self._uart_thread.start()
        
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
        
        # Publish offline status
        if self.mqtt_client and self.mqtt_client.is_connected():
            offline_status = json.dumps({"up": False, "ts": now_ts()})
            self.mqtt_client.publish(TOPIC_GATEWAY_STATUS, offline_status, qos=1, retain=True)
            self.mqtt_client.disconnect()
        
        # Stop UART
        self.uart.stop()
        
        logger.info("Gateway stopped")
    
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
            
            # Publish online status (retained)
            online_status = json.dumps({"up": True, "ts": now_ts()})
            client.publish(TOPIC_GATEWAY_STATUS, online_status, qos=1, retain=True)
            
            # Subscribe to command topic
            client.subscribe(TOPIC_CMD_VALVE, qos=1)
            logger.info(f"✓ Subscribed to {TOPIC_CMD_VALVE}")
        else:
            logger.error(f"MQTT connect failed with code {rc}")
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnect callback."""
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc}), will auto-reconnect")
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
            self._publish_ack(cid, False, rule_reason)
            return
        
        # Send command to UART
        cmd_line = make_cmd_line(payload)
        logger.debug(f"Sending to UART: {cmd_line.strip()}")
        
        if not self.uart.write_line(cmd_line):
            self._publish_ack(cid, False, "uart_write_failed")
            return
        
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
            elif msg_type == "LOG":
                logger.info(f"UART LOG: {payload}")
            elif msg_type == "ERR":
                logger.warning(f"UART parse error: {payload}")
        
        logger.info("UART reader thread stopped")
    
    def _handle_uart_data(self, data: dict) -> None:
        """Handle @DATA from UART."""
        # Update state cache
        self.state.update_from_data(data)
        
        # Publish telemetry (non-retained)
        telemetry = {
            "flow": self.state.flow,
            "battery": self.state.battery,
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
    
    def _handle_uart_ack(self, ack: dict) -> None:
        """Handle @ACK from UART."""
        cid = ack.get("cid")
        if cid:
            resolved = self.ack_router.resolve(cid, ack)
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
