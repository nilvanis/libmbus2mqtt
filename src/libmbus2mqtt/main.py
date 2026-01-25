"""Main application loop."""

from __future__ import annotations

import signal
import time
from typing import TYPE_CHECKING, Any

from libmbus2mqtt.logging import get_logger
from libmbus2mqtt.mbus.interface import MbusInterface
from libmbus2mqtt.models.device import AvailabilityStatus, Device
from libmbus2mqtt.mqtt import (
    BridgeInfo,
    CommandHandler,
    HomeAssistantDiscovery,
    MqttClient,
)

if TYPE_CHECKING:
    from libmbus2mqtt.config import AppConfig

logger = get_logger("main")


class Daemon:
    """Main daemon class managing the polling loop."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._running = False
        self._rescan_requested = False
        self._poll_interval = config.polling.interval

        # Components
        self._mbus: MbusInterface | None = None
        self._mqtt: MqttClient | None = None
        self._ha_discovery: HomeAssistantDiscovery | None = None
        self._bridge_info: BridgeInfo | None = None
        self._command_handler: CommandHandler | None = None

        # Device registry
        self._devices: dict[int, Device] = {}

    def start(self) -> None:
        """Start the daemon."""
        logger.info("Starting libmbus2mqtt daemon...")
        logger.info(f"M-Bus device: {self.config.mbus.device}")
        logger.info(f"MQTT broker: {self.config.mqtt.host}:{self.config.mqtt.port}")
        logger.info(
            f"Home Assistant: {'enabled' if self.config.homeassistant.enabled else 'disabled'}"
        )
        logger.info(f"Poll interval: {self._poll_interval}s")

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            # Initialize M-Bus interface
            self._init_mbus()

            # Initialize MQTT client
            self._init_mqtt()

            # Initialize devices from config
            self._init_devices()

            # Run initial scan if autoscan enabled
            if self.config.mbus.autoscan:
                self._scan_devices()

            # Startup delay
            if self.config.polling.startup_delay > 0:
                logger.info(f"Waiting {self.config.polling.startup_delay}s before first poll...")
                time.sleep(self.config.polling.startup_delay)

            # Main loop
            self._running = True
            self._run_loop()

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
        finally:
            self._cleanup()

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, shutting down...")
        self._running = False

    def _init_mbus(self) -> None:
        """Initialize M-Bus interface."""
        logger.info("Initializing M-Bus interface...")
        self._mbus = MbusInterface(
            device=self.config.mbus.device,
            baudrate=self.config.mbus.baudrate,
            retry_count=self.config.mbus.retry_count,
            retry_delay=self.config.mbus.retry_delay,
        )
        if self._mbus.endpoint.type == "tcp":
            logger.info(
                "M-Bus endpoint: TCP %s:%s (baudrate ignored)",
                self._mbus.endpoint.host,
                self._mbus.endpoint.port,
            )
        else:
            logger.info(
                "M-Bus endpoint: serial %s @ %s baud",
                self._mbus.device,
                self._mbus.baudrate,
            )

    def _init_mqtt(self) -> None:
        """Initialize MQTT client and related components."""
        logger.info("Connecting to MQTT broker...")

        self._mqtt = MqttClient(self.config.mqtt)
        self._mqtt.on_connect(self._on_mqtt_connect)
        self._mqtt.on_disconnect(self._on_mqtt_disconnect)
        self._mqtt.connect()

        # Initialize bridge info
        self._bridge_info = BridgeInfo(self._mqtt)
        self._bridge_info.set_poll_interval(self._poll_interval)

        # Initialize command handler
        self._command_handler = CommandHandler(self._mqtt)
        self._command_handler.on_rescan(self._request_rescan)
        self._command_handler.on_poll_interval_change(self._set_poll_interval)
        self._command_handler.setup()

        # Initialize HA discovery if enabled
        if self.config.homeassistant.enabled:
            self._ha_discovery = HomeAssistantDiscovery(
                self._mqtt,
                self.config.homeassistant,
            )

    def _init_devices(self) -> None:
        """Initialize devices from config."""
        for device_config in self.config.devices:
            device = Device(
                address=device_config.id,
                name=device_config.name,
                enabled=device_config.enabled,
                template_name=device_config.template,
            )
            device.availability.timeout_threshold = self.config.availability.timeout_polls
            self._devices[device_config.id] = device
            logger.debug(f"Added device from config: address={device_config.id}")

    def _scan_devices(self) -> None:
        """Scan for M-Bus devices."""
        if self._mbus is None:
            return

        logger.info("Scanning for M-Bus devices...")
        device_ids = self._mbus.scan()

        for device_id in device_ids:
            if device_id not in self._devices:
                device = Device(address=device_id)
                device.availability.timeout_threshold = self.config.availability.timeout_polls
                self._devices[device_id] = device
                logger.info(f"Discovered new device at address {device_id}")

        if self._bridge_info:
            self._bridge_info.set_discovered_devices(len(self._devices))
            self._bridge_info.set_last_scan()

    def _on_mqtt_connect(self) -> None:
        """Handle MQTT connection established."""
        logger.info("MQTT connected, publishing discovery configs...")

        # Publish bridge discovery
        if self._ha_discovery:
            self._ha_discovery.publish_bridge_discovery()

        # Publish device discovery for known devices
        for device in self._devices.values():
            if device.enabled and device.mbus_data:
                self._publish_device_discovery(device)

        # Publish bridge info
        if self._bridge_info:
            self._bridge_info.publish()

    def _on_mqtt_disconnect(self) -> None:
        """Handle MQTT disconnection."""
        logger.warning("MQTT disconnected, will attempt to reconnect...")

    def _request_rescan(self) -> None:
        """Request a device rescan on next loop iteration."""
        logger.info("Rescan requested via MQTT command")
        self._rescan_requested = True

    def _set_poll_interval(self, interval: int) -> None:
        """Update poll interval."""
        self._poll_interval = interval
        if self._bridge_info:
            self._bridge_info.set_poll_interval(interval)
            self._bridge_info.publish()

    def _run_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            loop_start = time.time()

            # Handle rescan request
            if self._rescan_requested:
                self._scan_devices()
                self._rescan_requested = False

            # Poll all enabled devices
            self._poll_devices()

            # Update bridge info
            self._update_bridge_info(loop_start)

            # Wait for next poll interval
            elapsed = time.time() - loop_start
            sleep_time = max(0, self._poll_interval - elapsed)

            if sleep_time > 0:
                logger.debug(f"Sleeping for {sleep_time:.1f}s")
                # Sleep in small chunks to allow for clean shutdown
                sleep_end = time.time() + sleep_time
                while self._running and time.time() < sleep_end:
                    time.sleep(min(1.0, sleep_end - time.time()))

    def _poll_devices(self) -> None:
        """Poll all enabled devices."""
        if self._mbus is None or self._mqtt is None:
            return

        online_count = 0

        for device in self._devices.values():
            if not device.enabled:
                continue

            mbus_data = self._mbus.poll(
                device.address,
                timeout=self.config.mbus.timeout,
            )

            if mbus_data:
                # Update device with new data
                first_data = device.mbus_data is None
                device.update_from_mbus_data(mbus_data)
                device.availability.poll_success()
                online_count += 1

                # Publish HA discovery on first successful poll
                if first_data and self._ha_discovery:
                    self._publish_device_discovery(device)

                # Publish state
                state: dict[str, Any]
                if device.ha_template:
                    state = mbus_data.to_ha_state(device.ha_template)
                else:
                    state = mbus_data.to_generic_state()
                self._mqtt.publish_device_state(device.object_id, state)

                logger.debug(f"Polled device {device.address}: success")
            else:
                device.availability.poll_fail()
                logger.warning(
                    f"Poll failed for device {device.address} "
                    f"({device.availability.poll_consecutive_fails} consecutive)"
                )

            # Publish availability if changed
            if device.availability.status_changed:
                self._mqtt.publish_device_availability(
                    device.object_id,
                    device.availability.status.value,
                )
                device.availability.reset_changed_flag()

        if self._bridge_info:
            self._bridge_info.set_online_devices(online_count)

    def _publish_device_discovery(self, device: Device) -> None:
        """Publish HA discovery for a device."""
        if self._ha_discovery and device.mbus_data:
            self._ha_discovery.publish_device_discovery(device)

    def _update_bridge_info(self, loop_start: float) -> None:
        """Update and publish bridge info."""
        if self._bridge_info:
            duration_ms = int((time.time() - loop_start) * 1000)
            self._bridge_info.set_last_poll_duration(duration_ms)
            self._bridge_info.publish()

    def _cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up...")

        # Mark all devices offline
        if self._mqtt:
            for device in self._devices.values():
                if device.availability.status == AvailabilityStatus.ONLINE:
                    self._mqtt.publish_device_availability(
                        device.object_id,
                        AvailabilityStatus.OFFLINE.value,
                    )

        # Disconnect MQTT
        if self._mqtt:
            self._mqtt.disconnect()

        logger.info("Shutdown complete")


def run_daemon(config: AppConfig) -> None:
    """Run the main daemon loop."""
    daemon = Daemon(config)
    daemon.start()
