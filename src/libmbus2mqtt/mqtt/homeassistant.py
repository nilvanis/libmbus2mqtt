"""Home Assistant MQTT Discovery integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from libmbus2mqtt.constants import (
    APP_NAME,
    APP_VERSION,
    HA_DEFAULT_DISCOVERY_PREFIX,
    TOPIC_BRIDGE_STATE,
    TOPIC_DEVICE_AVAILABILITY,
    TOPIC_DEVICE_STATE,
)
from libmbus2mqtt.logging import get_logger
from libmbus2mqtt.templates import get_template_for_device

if TYPE_CHECKING:
    from libmbus2mqtt.config import HomeAssistantConfig
    from libmbus2mqtt.models.device import Device
    from libmbus2mqtt.mqtt.client import MqttClient

logger = get_logger("mqtt.homeassistant")

# Bridge device identifier
BRIDGE_DEVICE_ID = f"{APP_NAME}_bridge"


def get_bridge_device_info() -> dict[str, Any]:
    """Get device info for the bridge device."""
    return {
        "identifiers": [BRIDGE_DEVICE_ID],
        "name": f"{APP_NAME} Bridge",
        "manufacturer": "libmbus2mqtt",
        "model": "Bridge",
        "sw_version": APP_VERSION,
    }


def get_mbus_device_info(device: Device) -> dict[str, Any]:
    """Get device info for an M-Bus device."""
    device_info: dict[str, Any] = {
        "identifiers": [f"{APP_NAME}_{device.object_id}"],
        "name": device.display_name,
        "via_device": BRIDGE_DEVICE_ID,
    }

    if device.manufacturer:
        device_info["manufacturer"] = device.manufacturer
    if device.model:
        device_info["model"] = device.model
    if device.serial_number:
        device_info["serial_number"] = device.serial_number
    if device.version:
        device_info["sw_version"] = device.version

    return device_info


class HomeAssistantDiscovery:
    """Home Assistant MQTT Discovery manager."""

    def __init__(
        self,
        mqtt_client: MqttClient,
        config: HomeAssistantConfig,
    ) -> None:
        self.mqtt = mqtt_client
        self.config = config
        self._published_entities: set[str] = set()

    @property
    def discovery_prefix(self) -> str:
        """Get the HA discovery prefix."""
        return self.config.discovery_prefix or HA_DEFAULT_DISCOVERY_PREFIX

    @property
    def base_topic(self) -> str:
        """Get the base MQTT topic."""
        return self.mqtt.base_topic

    def publish_bridge_discovery(self) -> None:
        """Publish HA discovery configs for bridge entities."""
        if not self.config.enabled:
            return

        logger.info("Publishing Home Assistant bridge discovery")

        bridge_device = get_bridge_device_info()
        base = self.base_topic

        # Discovered Devices sensor
        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_discovered_devices",
            name="Discovered Devices",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.discovered_devices }}",
            icon="mdi:devices",
        )

        # Online Devices sensor
        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_online_devices",
            name="Online Devices",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.online_devices }}",
            icon="mdi:check-network",
        )

        # Firmware Version sensor
        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_version",
            name="Firmware Version",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.version }}",
            icon="mdi:tag",
            entity_category="diagnostic",
        )

        # Last Scan sensor (disabled by default)
        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_last_scan",
            name="Last Scan",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.last_scan }}",
            icon="mdi:update",
            entity_category="diagnostic",
            enabled_by_default=False,
        )

        # Uptime sensor (disabled by default)
        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_uptime",
            name="Uptime",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.uptime }}",
            icon="mdi:timer-outline",
            entity_category="diagnostic",
            enabled_by_default=False,
        )

        # Last Poll Duration sensor (disabled by default)
        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_last_poll_duration",
            name="Last Poll Duration",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.last_poll_duration_ms }}",
            unit_of_measurement="ms",
            icon="mdi:timer",
            entity_category="diagnostic",
            enabled_by_default=False,
        )

        # Rescan Devices button
        self._publish_button(
            object_id=f"{BRIDGE_DEVICE_ID}_rescan",
            name="Rescan Devices",
            device=bridge_device,
            command_topic=f"{base}/command/rescan",
            icon="mdi:magnify-scan",
        )

        # Log Level select
        self._publish_select(
            object_id=f"{BRIDGE_DEVICE_ID}_log_level",
            name="Log Level",
            device=bridge_device,
            command_topic=f"{base}/command/log_level",
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.log_level }}",
            options=["DEBUG", "INFO", "WARNING", "ERROR"],
            icon="mdi:text-box-outline",
            entity_category="config",
        )

        # Poll Interval number
        self._publish_number(
            object_id=f"{BRIDGE_DEVICE_ID}_poll_interval",
            name="Poll Interval",
            device=bridge_device,
            command_topic=f"{base}/command/poll_interval",
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.poll_interval }}",
            min_value=10,
            max_value=3600,
            step=1,
            unit_of_measurement="s",
            icon="mdi:update",
            entity_category="config",
        )

    def publish_device_discovery(self, device: Device) -> None:
        """Publish HA discovery configs for an M-Bus device."""
        if not self.config.enabled:
            return

        logger.info(f"Publishing HA discovery for device {device.object_id}")

        device_info = get_mbus_device_info(device)
        base = self.base_topic
        device_id = device.object_id

        # State/availability topics for this device
        state_topic = TOPIC_DEVICE_STATE.format(base=base, device_id=device_id)
        availability_topic = TOPIC_DEVICE_AVAILABILITY.format(base=base, device_id=device_id)
        availability_list = self._build_device_availability_list(availability_topic)

        # Try to load a template for this device
        template = None
        if device.manufacturer:
            template = get_template_for_device(device.manufacturer, device.model)
            if template:
                logger.debug(f"Using template for {device.manufacturer}/{device.model}")
                device.ha_template = template

        if template:
            # Use template-defined entities
            self._publish_template_entities(
                device=device,
                device_info=device_info,
                template=template,
                state_topic=state_topic,
                availability=availability_list,
            )
        else:
            # Publish generic entities based on data records
            self._publish_generic_entities(
                device=device,
                device_info=device_info,
                state_topic=state_topic,
                availability=availability_list,
            )

        device.ha_discovery_published = True

    def _publish_template_entities(
        self,
        device: Device,
        device_info: dict[str, Any],
        template: dict[str, dict[str, str]],
        state_topic: str,
        availability: list[dict[str, str]],
    ) -> None:
        """Publish entities defined in a device template."""
        for entity_id, entity_config in template.items():
            component = entity_config.get("component", "sensor")
            object_id = f"{APP_NAME}_{device.object_id}_{entity_id}"

            config: dict[str, Any] = {
                "name": entity_config.get("name", entity_id),
                "unique_id": object_id,
                "device": device_info,
                "state_topic": state_topic,
                "availability": availability,
            }

            # Add value template if specified
            if "value_template" in entity_config:
                config["value_template"] = entity_config["value_template"]

            # Add optional fields
            for field in [
                "device_class",
                "unit_of_measurement",
                "state_class",
                "icon",
            ]:
                if field in entity_config:
                    config[field] = entity_config[field]

            self.mqtt.publish_ha_discovery(
                component=component,
                object_id=object_id,
                config=config,
                discovery_prefix=self.discovery_prefix,
            )
            self._published_entities.add(f"{component}/{object_id}")

    def _publish_generic_entities(
        self,
        device: Device,
        device_info: dict[str, Any],
        state_topic: str,
        availability: list[dict[str, str]],
    ) -> None:
        """Publish generic entities based on M-Bus data records."""
        if not device.mbus_data:
            logger.warning(f"No M-Bus data for device {device.object_id}")
            return

        for record_key, record in device.mbus_data.data_records.items():
            if record.value is None:
                continue

            # Create sensor for each data record
            record_id = f"record_{record_key}" if record_key else f"func_{record.function}"
            object_id = f"{APP_NAME}_{device.object_id}_{record_id}"

            config: dict[str, Any] = {
                "name": record.function or f"Record {record_key}",
                "unique_id": object_id,
                "device": device_info,
                "state_topic": state_topic,
                "value_template": f"{{{{ value_json.records['{record_key}'].value }}}}",
                "availability": availability,
            }

            if record.unit:
                config["unit_of_measurement"] = record.unit

            # Try to infer device class from function name
            device_class = self._infer_device_class(record.function)
            if device_class:
                config["device_class"] = device_class
                config["state_class"] = "total_increasing"

            self.mqtt.publish_ha_discovery(
                component="sensor",
                object_id=object_id,
                config=config,
                discovery_prefix=self.discovery_prefix,
            )
            self._published_entities.add(f"sensor/{object_id}")

    def _infer_device_class(self, function: str | None) -> str | None:
        """Infer HA device class from M-Bus function name."""
        if not function:
            return None

        function_lower = function.lower()

        if "volume" in function_lower or "water" in function_lower:
            return "water"
        if "energy" in function_lower or "heat" in function_lower:
            return "energy"
        if "power" in function_lower:
            return "power"
        if "temperature" in function_lower:
            return "temperature"
        if "pressure" in function_lower:
            return "pressure"
        if "flow" in function_lower:
            return "volume_flow_rate"

        return None

    def _build_device_availability_list(self, device_availability_topic: str) -> list[dict[str, str]]:
        """Build HA availability list combining bridge and device availability topics."""
        return [
            {
                "topic": TOPIC_BRIDGE_STATE.format(base=self.base_topic),
                "payload_available": "online",
                "payload_not_available": "offline",
            },
            {
                "topic": device_availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
            },
        ]

    def _publish_sensor(
        self,
        object_id: str,
        name: str,
        device: dict[str, Any],
        state_topic: str,
        value_template: str,
        icon: str | None = None,
        unit_of_measurement: str | None = None,
        device_class: str | None = None,
        state_class: str | None = None,
        entity_category: str | None = None,
        enabled_by_default: bool = True,
    ) -> None:
        """Publish a sensor discovery config."""
        config: dict[str, Any] = {
            "name": name,
            "unique_id": object_id,
            "device": device,
            "state_topic": state_topic,
            "value_template": value_template,
            "availability": [
                {
                    "topic": TOPIC_BRIDGE_STATE.format(base=self.base_topic),
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
            ],
        }

        if icon:
            config["icon"] = icon
        if unit_of_measurement:
            config["unit_of_measurement"] = unit_of_measurement
        if device_class:
            config["device_class"] = device_class
        if state_class:
            config["state_class"] = state_class
        if entity_category:
            config["entity_category"] = entity_category
        if not enabled_by_default:
            config["enabled_by_default"] = False

        self.mqtt.publish_ha_discovery(
            component="sensor",
            object_id=object_id,
            config=config,
            discovery_prefix=self.discovery_prefix,
        )
        self._published_entities.add(f"sensor/{object_id}")

    def _publish_button(
        self,
        object_id: str,
        name: str,
        device: dict[str, Any],
        command_topic: str,
        icon: str | None = None,
        entity_category: str | None = None,
    ) -> None:
        """Publish a button discovery config."""
        config: dict[str, Any] = {
            "name": name,
            "unique_id": object_id,
            "device": device,
            "command_topic": command_topic,
            "availability": [
                {
                    "topic": TOPIC_BRIDGE_STATE.format(base=self.base_topic),
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
            ],
        }

        if icon:
            config["icon"] = icon
        if entity_category:
            config["entity_category"] = entity_category

        self.mqtt.publish_ha_discovery(
            component="button",
            object_id=object_id,
            config=config,
            discovery_prefix=self.discovery_prefix,
        )
        self._published_entities.add(f"button/{object_id}")

    def _publish_select(
        self,
        object_id: str,
        name: str,
        device: dict[str, Any],
        command_topic: str,
        state_topic: str,
        value_template: str,
        options: list[str],
        icon: str | None = None,
        entity_category: str | None = None,
    ) -> None:
        """Publish a select discovery config."""
        config: dict[str, Any] = {
            "name": name,
            "unique_id": object_id,
            "device": device,
            "command_topic": command_topic,
            "state_topic": state_topic,
            "value_template": value_template,
            "options": options,
            "availability": [
                {
                    "topic": TOPIC_BRIDGE_STATE.format(base=self.base_topic),
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
            ],
        }

        if icon:
            config["icon"] = icon
        if entity_category:
            config["entity_category"] = entity_category

        self.mqtt.publish_ha_discovery(
            component="select",
            object_id=object_id,
            config=config,
            discovery_prefix=self.discovery_prefix,
        )
        self._published_entities.add(f"select/{object_id}")

    def _publish_number(
        self,
        object_id: str,
        name: str,
        device: dict[str, Any],
        command_topic: str,
        state_topic: str,
        value_template: str,
        min_value: float,
        max_value: float,
        step: float = 1,
        unit_of_measurement: str | None = None,
        icon: str | None = None,
        entity_category: str | None = None,
    ) -> None:
        """Publish a number discovery config."""
        config: dict[str, Any] = {
            "name": name,
            "unique_id": object_id,
            "device": device,
            "command_topic": command_topic,
            "state_topic": state_topic,
            "value_template": value_template,
            "min": min_value,
            "max": max_value,
            "step": step,
            "availability": [
                {
                    "topic": TOPIC_BRIDGE_STATE.format(base=self.base_topic),
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
            ],
        }

        if unit_of_measurement:
            config["unit_of_measurement"] = unit_of_measurement
        if icon:
            config["icon"] = icon
        if entity_category:
            config["entity_category"] = entity_category

        self.mqtt.publish_ha_discovery(
            component="number",
            object_id=object_id,
            config=config,
            discovery_prefix=self.discovery_prefix,
        )
        self._published_entities.add(f"number/{object_id}")

    def remove_all_discovery(self) -> None:
        """Remove all published HA discovery configs."""
        logger.info("Removing all Home Assistant discovery configs")

        for entity_key in self._published_entities:
            component, object_id = entity_key.split("/", 1)
            self.mqtt.remove_ha_discovery(
                component=component,
                object_id=object_id,
                discovery_prefix=self.discovery_prefix,
            )

        self._published_entities.clear()
