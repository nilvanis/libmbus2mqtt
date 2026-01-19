"""MQTT client wrapper with threading support."""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import paho.mqtt.client as mqtt

from libmbus2mqtt.constants import (
    APP_NAME,
    TOPIC_BRIDGE_STATE,
    TOPIC_COMMAND_LOG_LEVEL,
    TOPIC_COMMAND_POLL_INTERVAL,
    TOPIC_COMMAND_RESCAN,
    TOPIC_DEVICE_AVAILABILITY,
    TOPIC_DEVICE_STATE,
)
from libmbus2mqtt.logging import get_logger

if TYPE_CHECKING:
    from libmbus2mqtt.config import MqttConfig

logger = get_logger("mqtt.client")

# Callback types
CommandCallback = Callable[[str, str], None]


class MqttClient:
    """MQTT client with threading support."""

    def __init__(self, config: MqttConfig) -> None:
        self.config = config
        self._client: mqtt.Client | None = None
        self._connected = threading.Event()
        self._stopping = False
        self._command_callbacks: dict[str, CommandCallback] = {}
        self._on_connect_callback: Callable[[], None] | None = None
        self._on_disconnect_callback: Callable[[], None] | None = None

    @property
    def base_topic(self) -> str:
        """Get the base MQTT topic."""
        return self.config.base_topic

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected.is_set()

    def _get_client_id(self) -> str:
        """Generate or return configured client ID."""
        if self.config.client_id:
            return self.config.client_id
        return f"{APP_NAME}_{uuid.uuid4().hex[:8]}"

    def connect(self) -> None:
        """Connect to MQTT broker."""
        client_id = self._get_client_id()
        logger.info(f"Connecting to MQTT broker {self.config.host}:{self.config.port}")

        self._client = mqtt.Client(
            client_id=client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined]
        )

        # Set up callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        # Set credentials if provided
        if self.config.username:
            self._client.username_pw_set(
                self.config.username,
                self.config.password,
            )

        # Set last will for bridge availability
        will_topic = TOPIC_BRIDGE_STATE.format(base=self.base_topic)
        self._client.will_set(will_topic, "offline", qos=1, retain=True)

        # Connect
        self._client.connect(
            self.config.host,
            self.config.port,
            keepalive=self.config.keepalive,
        )

        # Start network loop in background thread
        self._client.loop_start()

        # Wait for connection
        if not self._connected.wait(timeout=10):
            logger.error("Failed to connect to MQTT broker within timeout")
            raise ConnectionError("MQTT connection timeout")

    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        self._stopping = True
        if self._client is None:
            return

        # Publish offline status before disconnecting
        self.publish_bridge_state("offline")

        self._client.loop_stop()
        self._client.disconnect()
        self._connected.clear()
        logger.info("Disconnected from MQTT broker")

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        """Handle connection established."""
        # Check for successful connection (rc=0)
        rc = getattr(reason_code, "value", reason_code)
        if rc == 0:
            logger.info("Connected to MQTT broker")
            self._connected.set()

            # Subscribe to command topics
            self._subscribe_to_commands()

            # Publish online status
            self.publish_bridge_state("online")

            # Call user callback if set
            if self._on_connect_callback:
                self._on_connect_callback()
        else:
            logger.error(f"Failed to connect: {reason_code}")

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        """Handle disconnection."""
        self._connected.clear()
        if not self._stopping:
            logger.warning(f"Disconnected from MQTT broker: {reason_code}")
            if self._on_disconnect_callback:
                self._on_disconnect_callback()

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Handle incoming messages."""
        topic = message.topic
        payload = message.payload.decode("utf-8", errors="replace")
        logger.debug(f"Received message on {topic}: {payload}")

        # Check if this is a command topic
        for command_topic, callback in self._command_callbacks.items():
            if topic == command_topic:
                try:
                    callback(topic, payload)
                except Exception as e:
                    logger.error(f"Error handling command on {topic}: {e}")
                break

    def _subscribe_to_commands(self) -> None:
        """Subscribe to command topics."""
        if self._client is None:
            return

        command_topics = [
            TOPIC_COMMAND_RESCAN.format(base=self.base_topic),
            TOPIC_COMMAND_LOG_LEVEL.format(base=self.base_topic),
            TOPIC_COMMAND_POLL_INTERVAL.format(base=self.base_topic),
        ]

        for topic in command_topics:
            self._client.subscribe(topic, qos=self.config.qos)
            logger.debug(f"Subscribed to {topic}")

    def register_command_callback(
        self,
        topic_template: str,
        callback: CommandCallback,
    ) -> None:
        """Register a callback for a command topic."""
        topic = topic_template.format(base=self.base_topic)
        self._command_callbacks[topic] = callback
        logger.debug(f"Registered command callback for {topic}")

    def on_connect(self, callback: Callable[[], None]) -> None:
        """Set callback for connection events."""
        self._on_connect_callback = callback

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Set callback for disconnection events."""
        self._on_disconnect_callback = callback

    def publish(
        self,
        topic: str,
        payload: str | dict[str, Any],
        qos: int | None = None,
        retain: bool = False,
    ) -> bool:
        """Publish a message to a topic."""
        if self._client is None or not self.is_connected:
            logger.warning(f"Cannot publish to {topic}: not connected")
            return False

        if isinstance(payload, dict):
            payload = json.dumps(payload)

        result = self._client.publish(
            topic,
            payload,
            qos=qos if qos is not None else self.config.qos,
            retain=retain,
        )

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning(f"Failed to publish to {topic}: {result.rc}")
            return False

        return True

    def publish_bridge_state(self, state: str) -> bool:
        """Publish bridge availability state."""
        topic = TOPIC_BRIDGE_STATE.format(base=self.base_topic)
        return self.publish(topic, state, retain=True)

    def publish_device_state(
        self,
        device_id: str,
        state: dict[str, Any],
    ) -> bool:
        """Publish device state data."""
        topic = TOPIC_DEVICE_STATE.format(
            base=self.base_topic,
            device_id=device_id,
        )
        return self.publish(topic, state, retain=True)

    def publish_device_availability(
        self,
        device_id: str,
        status: str,
    ) -> bool:
        """Publish device availability status."""
        topic = TOPIC_DEVICE_AVAILABILITY.format(
            base=self.base_topic,
            device_id=device_id,
        )
        return self.publish(topic, status, retain=True)

    def publish_ha_discovery(
        self,
        component: str,
        object_id: str,
        config: dict[str, Any],
        discovery_prefix: str = "homeassistant",
    ) -> bool:
        """Publish Home Assistant discovery config."""
        topic = f"{discovery_prefix}/{component}/{object_id}/config"
        return self.publish(topic, config, retain=True)

    def remove_ha_discovery(
        self,
        component: str,
        object_id: str,
        discovery_prefix: str = "homeassistant",
    ) -> bool:
        """Remove Home Assistant discovery config."""
        topic = f"{discovery_prefix}/{component}/{object_id}/config"
        return self.publish(topic, "", retain=True)
