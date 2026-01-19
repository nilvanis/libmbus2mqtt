"""MQTT command handler for bridge commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from libmbus2mqtt.constants import (
    TOPIC_COMMAND_LOG_LEVEL,
    TOPIC_COMMAND_POLL_INTERVAL,
    TOPIC_COMMAND_RESCAN,
)
from libmbus2mqtt.logging import get_logger, set_log_level

if TYPE_CHECKING:
    from libmbus2mqtt.mqtt.client import MqttClient

logger = get_logger("mqtt.commands")


class CommandHandler:
    """Handles MQTT command messages."""

    def __init__(self, mqtt_client: MqttClient) -> None:
        self.mqtt = mqtt_client
        self._rescan_callback: Callable[[], None] | None = None
        self._poll_interval_callback: Callable[[int], None] | None = None

    def setup(self) -> None:
        """Register command callbacks with MQTT client."""
        self.mqtt.register_command_callback(
            TOPIC_COMMAND_RESCAN,
            self._handle_rescan,
        )
        self.mqtt.register_command_callback(
            TOPIC_COMMAND_LOG_LEVEL,
            self._handle_log_level,
        )
        self.mqtt.register_command_callback(
            TOPIC_COMMAND_POLL_INTERVAL,
            self._handle_poll_interval,
        )
        logger.debug("Command handlers registered")

    def on_rescan(self, callback: Callable[[], None]) -> None:
        """Set callback for rescan command."""
        self._rescan_callback = callback

    def on_poll_interval_change(self, callback: Callable[[int], None]) -> None:
        """Set callback for poll interval change."""
        self._poll_interval_callback = callback

    def _handle_rescan(self, topic: str, payload: str) -> None:
        """Handle rescan command."""
        logger.info("Received rescan command")
        if self._rescan_callback:
            self._rescan_callback()

    def _handle_log_level(self, topic: str, payload: str) -> None:
        """Handle log level change command."""
        level = payload.strip().upper()
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]

        if level not in valid_levels:
            logger.warning(f"Invalid log level: {level}")
            return

        logger.info(f"Setting log level to {level}")
        set_log_level(level)

    def _handle_poll_interval(self, topic: str, payload: str) -> None:
        """Handle poll interval change command."""
        try:
            interval = int(payload.strip())
        except ValueError:
            logger.warning(f"Invalid poll interval: {payload}")
            return

        if interval < 10 or interval > 3600:
            logger.warning(f"Poll interval out of range: {interval}")
            return

        logger.info(f"Setting poll interval to {interval}s")
        if self._poll_interval_callback:
            self._poll_interval_callback(interval)
