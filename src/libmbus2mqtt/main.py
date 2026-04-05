"""Main application loop."""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from libmbus2mqtt.constants import APP_VERSION
from libmbus2mqtt.logging import get_logger
from libmbus2mqtt.mbus.interface import MbusInterface
from libmbus2mqtt.models.device import AvailabilityStatus, Device
from libmbus2mqtt.mqtt import (
    BridgeInfo,
    CommandHandler,
    HomeAssistantDiscovery,
    MqttClient,
)
from libmbus2mqtt.state import StateStore, build_identity_key, utcnow_iso

if TYPE_CHECKING:
    from libmbus2mqtt.config import AppConfig

logger = get_logger("main")


@dataclass(frozen=True)
class DeviceSyncResult:
    """Outcome of syncing a polled device with persisted runtime state."""

    should_publish_discovery: bool
    renamed: bool = False
    template_rematched: bool = False
    identity_changed: bool = False


class Daemon:
    """Main daemon class managing the polling loop."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._running = False
        self._rescan_requested = False
        self._poll_interval = config.mbus.poll_interval

        # Components
        self._mbus: MbusInterface | None = None
        self._mqtt: MqttClient | None = None
        self._ha_discovery: HomeAssistantDiscovery | None = None
        self._bridge_info: BridgeInfo | None = None
        self._command_handler: CommandHandler | None = None
        self._state_store: StateStore | None = None

        # Device registry
        self._devices: dict[int, Device] = {}

    def start(self) -> None:
        """Start the daemon."""
        logger.info(f"Starting libmbus2mqtt v{APP_VERSION}...")
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
            # Initialize state store
            self._init_state_store()

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
            if self.config.mbus.startup_delay > 0:
                logger.info(f"Waiting {self.config.mbus.startup_delay}s before first poll...")
                time.sleep(self.config.mbus.startup_delay)

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
                "M-Bus endpoint: TCP %s:%s",
                self._mbus.endpoint.host,
                self._mbus.endpoint.port,
            )
        else:
            logger.info(
                "M-Bus endpoint: serial %s @ %s baud",
                self._mbus.device,
                self._mbus.baudrate,
            )

    def _init_state_store(self) -> None:
        """Initialize persistent runtime state."""
        self._state_store = StateStore()

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
                self._state_store,
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

        logger.info("Initializing M-Bus scan...")
        device_ids = self._mbus.scan()

        for device_id in device_ids:
            if device_id not in self._devices:
                device = Device(address=device_id)
                device.availability.timeout_threshold = self.config.availability.timeout_polls
                self._devices[device_id] = device
                logger.info(f"Discovered new device at address {device_id} ({device.name})")

        if self._bridge_info:
            self._bridge_info.set_discovered_devices(len(self._devices))
            self._bridge_info.set_last_scan()
            self._bridge_info.publish()

    def _on_mqtt_connect(self) -> None:
        """Handle MQTT connection established."""
        logger.info("MQTT connected, publishing discovery configs...")

        # Publish bridge info first so state payload is retained before discovery
        if self._bridge_info:
            self._bridge_info.publish()

        # Publish bridge discovery
        if self._ha_discovery:
            self._ha_discovery.publish_bridge_discovery()

        # Publish device discovery for known devices
        for device in self._devices.values():
            if device.enabled and device.mbus_data and self._is_current_binding(device):
                self._publish_device_discovery(device)
                if (
                    device.availability.status != AvailabilityStatus.UNKNOWN
                    and self._mqtt is not None
                ):
                    self._mqtt.publish_device_availability(
                        device.object_id,
                        device.availability.status.value,
                    )

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

            sync_result = DeviceSyncResult(should_publish_discovery=False)
            mbus_data = self._mbus.poll(
                device.address,
                timeout=self.config.mbus.timeout,
            )

            if mbus_data:
                # Update device with new data
                first_data = device.mbus_data is None
                device.update_from_mbus_data(mbus_data)
                sync_result = self._sync_device_runtime_state(device, first_data)
                device.availability.poll_success()
                online_count += 1

                if sync_result.should_publish_discovery and self._ha_discovery:
                    self._publish_device_discovery(device)
                else:
                    self._restore_binding_template_metadata(device)

                self._persist_address_binding(device)

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
            force_publish_availability = mbus_data is not None and sync_result.identity_changed
            if (
                self._mqtt is not None
                and self._is_current_binding(device)
                and (force_publish_availability or device.availability.status_changed)
            ):
                self._mqtt.publish_device_availability(
                    device.object_id,
                    device.availability.status.value,
                )
                device.availability.reset_changed_flag()
            elif device.availability.status_changed:
                device.availability.reset_changed_flag()

        if self._bridge_info:
            self._bridge_info.set_online_devices(online_count)

    def _publish_device_discovery(self, device: Device) -> None:
        """Publish HA discovery for a device."""
        if self._ha_discovery and device.mbus_data:
            self._ha_discovery.publish_device_discovery(device)

    def _sync_device_runtime_state(self, device: Device, first_data: bool) -> DeviceSyncResult:
        """Sync runtime device state with the persistent SQLite store."""
        if self._state_store is None or self._mqtt is None:
            return DeviceSyncResult(should_publish_discovery=first_data)

        identity_tuple = device.identity_tuple
        if identity_tuple is None:
            return DeviceSyncResult(should_publish_discovery=first_data)

        object_id, manufacturer, model = identity_tuple
        identity_key = build_identity_key(object_id, manufacturer, model)
        device.identity_key = identity_key

        timestamp = utcnow_iso()
        binding = self._state_store.get_address_binding(device.address)
        current_identity = self._state_store.get_identity(identity_key)
        published_name = device.display_name

        if binding is None:
            event_type = "bootstrap"
            if current_identity is not None:
                event_type = "reactivate" if current_identity.status == "replaced" else "activate"
            self._state_store.upsert_identity(
                identity_key=identity_key,
                object_id=object_id,
                manufacturer=manufacturer,
                model=model,
                status="active",
                last_address=device.address,
                increment_activation=current_identity is None
                or current_identity.status != "active",
                seen_at=timestamp,
            )
            self._state_store.record_event(
                address=device.address,
                event_type=event_type,
                to_identity_key=identity_key,
                details={"datarecord_count": device.datarecord_count},
                created_at=timestamp,
            )
            return DeviceSyncResult(should_publish_discovery=True, identity_changed=not first_data)

        if binding.identity_key != identity_key:
            old_identity = self._state_store.get_identity(binding.identity_key)
            if old_identity is not None:
                self._state_store.set_identity_status(
                    old_identity.identity_key,
                    "replaced",
                    last_address=device.address,
                    seen_at=timestamp,
                )
                self._state_store.mark_entities_replaced(
                    old_identity.identity_key, updated_at=timestamp
                )
                replaced_name = f"{binding.published_device_name} (replaced)"
                if self._ha_discovery:
                    self._ha_discovery.publish_replaced_device(
                        old_identity.identity_key, replaced_name
                    )
                self._mqtt.publish_device_availability(
                    old_identity.object_id,
                    AvailabilityStatus.OFFLINE.value,
                )

            event_type = "activate"
            if current_identity is not None and current_identity.status == "replaced":
                event_type = "reactivate"

            self._state_store.upsert_identity(
                identity_key=identity_key,
                object_id=object_id,
                manufacturer=manufacturer,
                model=model,
                status="active",
                last_address=device.address,
                increment_activation=current_identity is None
                or current_identity.status != "active",
                seen_at=timestamp,
            )
            self._state_store.record_event(
                address=device.address,
                event_type="replace",
                from_identity_key=binding.identity_key,
                to_identity_key=identity_key,
                details={"datarecord_count": device.datarecord_count},
                created_at=timestamp,
            )
            self._state_store.record_event(
                address=device.address,
                event_type=event_type,
                from_identity_key=binding.identity_key,
                to_identity_key=identity_key,
                details={"datarecord_count": device.datarecord_count},
                created_at=timestamp,
            )
            return DeviceSyncResult(should_publish_discovery=True, identity_changed=True)

        self._state_store.upsert_identity(
            identity_key=identity_key,
            object_id=object_id,
            manufacturer=manufacturer,
            model=model,
            status="active",
            last_address=device.address,
            increment_activation=current_identity is None or current_identity.status != "active",
            seen_at=timestamp,
        )

        renamed = (
            binding.configured_name != device.name
            or binding.published_device_name != published_name
        )
        if renamed:
            self._state_store.record_event(
                address=device.address,
                event_type="rename",
                from_identity_key=identity_key,
                to_identity_key=identity_key,
                details={
                    "configured_name": device.name,
                    "published_device_name": published_name,
                },
                created_at=timestamp,
            )

        datarecord_count_changed = binding.datarecord_count != device.datarecord_count
        template_rematched = False
        if datarecord_count_changed:
            if device.template_name:
                logger.warning(
                    "Device %s record count changed from %s to %s but explicit template %s is pinned",
                    device.address,
                    binding.datarecord_count,
                    device.datarecord_count,
                    device.template_name,
                )
            else:
                template_rematched = True
                self._state_store.record_event(
                    address=device.address,
                    event_type="template_rematch",
                    from_identity_key=identity_key,
                    to_identity_key=identity_key,
                    details={
                        "old_datarecord_count": binding.datarecord_count,
                        "new_datarecord_count": device.datarecord_count,
                    },
                    created_at=timestamp,
                )

        return DeviceSyncResult(
            should_publish_discovery=first_data or renamed or template_rematched,
            renamed=renamed,
            template_rematched=template_rematched,
            identity_changed=False,
        )

    def _restore_binding_template_metadata(self, device: Device) -> None:
        """Restore persisted template metadata when discovery is not republished."""
        if self._state_store is None:
            return

        binding = self._state_store.get_address_binding(device.address)
        if binding is None or binding.identity_key != device.identity_key:
            if device.template_name:
                device.current_template_name = device.template_name
                device.current_template_mode = "explicit"
                device.current_template_source = "explicit"
            return

        device.current_template_name = binding.template_name
        device.current_template_mode = binding.template_mode
        device.current_template_source = binding.template_source

    def _is_current_binding(self, device: Device) -> bool:
        """Return whether the device still owns the active binding for its address."""
        if self._state_store is None or device.identity_key is None:
            return True

        binding = self._state_store.get_address_binding(device.address)
        return binding is not None and binding.identity_key == device.identity_key

    def _persist_address_binding(self, device: Device) -> None:
        """Persist the current active identity binding for an address."""
        if self._state_store is None or device.identity_key is None:
            return

        self._state_store.upsert_address_binding(
            address=device.address,
            identity_key=device.identity_key,
            configured_name=device.name,
            published_device_name=device.display_name,
            template_mode=device.current_template_mode,
            template_name=device.current_template_name,
            template_source=device.current_template_source,
            datarecord_count=device.datarecord_count,
        )

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
