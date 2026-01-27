"""Bridge state management and publishing."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from libmbus2mqtt.constants import APP_VERSION
from libmbus2mqtt.logging import get_logger

if TYPE_CHECKING:
    from libmbus2mqtt.mqtt.client import MqttClient

logger = get_logger("mqtt.bridge")


class BridgeInfo:
    """Manages and publishes bridge state information."""

    def __init__(self, mqtt_client: MqttClient) -> None:
        self.mqtt = mqtt_client
        self._start_time = datetime.now()
        self._discovered_devices = 0
        self._online_devices = 0
        self._last_scan: datetime | None = None
        self._last_poll_duration_ms: int | None = None
        self._log_level = "INFO"
        self._poll_interval = 60

    @property
    def base_topic(self) -> str:
        """Get the base MQTT topic."""
        return self.mqtt.base_topic

    @property
    def info_topic(self) -> str:
        """Get the bridge info topic."""
        return f"{self.base_topic}/bridge/info"

    @property
    def uptime(self) -> str:
        """Get formatted uptime string."""
        delta = datetime.now() - self._start_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def set_discovered_devices(self, count: int) -> None:
        """Update discovered device count."""
        self._discovered_devices = count

    def set_online_devices(self, count: int) -> None:
        """Update online device count."""
        self._online_devices = count

    def set_last_scan(self, timestamp: datetime | None = None) -> None:
        """Update last scan timestamp."""
        self._last_scan = timestamp or datetime.now()

    def set_last_poll_duration(self, duration_ms: int) -> None:
        """Update last poll duration."""
        self._last_poll_duration_ms = duration_ms

    def set_log_level(self, level: str) -> None:
        """Update current log level."""
        self._log_level = level.upper()

    def set_poll_interval(self, interval: int) -> None:
        """Update current poll interval."""
        self._poll_interval = interval

    def get_current_log_level(self) -> str:
        """Get current log level from logging system."""
        level = logging.getLogger("libmbus2mqtt").level
        return logging.getLevelName(level)

    def get_state(self) -> dict[str, Any]:
        """Get current bridge state as dict."""
        state: dict[str, Any] = {
            "version": APP_VERSION,
            "discovered_devices": self._discovered_devices,
            "online_devices": self._online_devices,
            "uptime": self.uptime,
            "log_level": self.get_current_log_level(),
            "poll_interval": self._poll_interval,
            "last_scan": self._last_scan.isoformat() if self._last_scan else None,
        }

        if self._last_poll_duration_ms is not None:
            state["last_poll_duration_ms"] = self._last_poll_duration_ms

        return state

    def publish(self) -> bool:
        """Publish bridge info to MQTT."""
        state = self.get_state()
        payload = json.dumps(state)
        return self.mqtt.publish(self.info_topic, payload, retain=True)
