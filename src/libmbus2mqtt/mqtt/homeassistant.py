"""Home Assistant MQTT Discovery integration."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from libmbus2mqtt.constants import (
    APP_NAME,
    APP_VERSION,
    HA_DEFAULT_DISCOVERY_PREFIX,
    TOPIC_BRIDGE_STATE,
    TOPIC_DEVICE_AVAILABILITY,
    TOPIC_DEVICE_ENTITY_AVAILABILITY,
    TOPIC_DEVICE_STATE,
)
from libmbus2mqtt.logging import get_logger
from libmbus2mqtt.templates import TemplateSelection, resolve_template

if TYPE_CHECKING:
    from libmbus2mqtt.config import HomeAssistantConfig
    from libmbus2mqtt.models.device import Device
    from libmbus2mqtt.mqtt.client import MqttClient
    from libmbus2mqtt.state import StateStore

logger = get_logger("mqtt.homeassistant")

# Bridge device identifier
BRIDGE_DEVICE_ID = f"{APP_NAME}_bridge"


@dataclass(frozen=True)
class PublishedDeviceEntity:
    """Published Home Assistant entity metadata."""

    discovery_object_id: str
    component: str
    entity_key: str
    discovery_topic: str
    entity_availability_topic: str | None
    config: dict[str, Any]


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
        state_store: StateStore | None = None,
    ) -> None:
        self.mqtt = mqtt_client
        self.config = config
        self.state_store = state_store
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

        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_discovered_devices",
            name="Discovered Devices",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.discovered_devices }}",
            icon="mdi:devices",
        )
        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_online_devices",
            name="Online Devices",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.online_devices }}",
            icon="mdi:check-network",
        )
        self._publish_sensor(
            object_id=f"{BRIDGE_DEVICE_ID}_version",
            name="Firmware Version",
            device=bridge_device,
            state_topic=f"{base}/bridge/info",
            value_template="{{ value_json.version }}",
            icon="mdi:tag",
            entity_category="diagnostic",
        )
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
        self._publish_button(
            object_id=f"{BRIDGE_DEVICE_ID}_rescan",
            name="Rescan Devices",
            device=bridge_device,
            command_topic=f"{base}/command/rescan",
            icon="mdi:magnify-scan",
        )
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

        logger.info(f"Publishing HA discovery for device ID {device.address}: {device.name}")

        device_info = get_mbus_device_info(device)
        device_id = device.object_id
        state_topic = TOPIC_DEVICE_STATE.format(base=self.base_topic, device_id=device_id)

        selection = self._resolve_device_template(device)
        device.current_template_name = selection.filename
        device.current_template_mode = selection.mode
        device.current_template_source = selection.source
        device.ha_template = selection.template

        published_entities: list[PublishedDeviceEntity]
        if selection.template:
            published_entities = self._publish_template_entities(
                device=device,
                device_info=device_info,
                template=selection.template,
                state_topic=state_topic,
                availability=[],
            )
        else:
            published_entities = self._publish_generic_entities(
                device=device,
                device_info=device_info,
                state_topic=state_topic,
                availability=[],
            )

        self._sync_published_entities(device, published_entities)
        device.ha_discovery_published = True

    def _publish_template_entities(
        self,
        device: Device,
        device_info: dict[str, Any],
        template: dict[str, dict[str, str]],
        state_topic: str,
        availability: list[dict[str, str]],
    ) -> list[PublishedDeviceEntity]:
        """Publish entities defined in a device template."""
        published_entities: list[PublishedDeviceEntity] = []
        for entity_id, entity_config in template.items():
            component = (
                entity_config.get("component")
                or entity_config.get("platform")
                or "sensor"
            )
            object_id = f"{APP_NAME}_{device.object_id}_{entity_id}"
            discovery_topic = self._get_discovery_topic(component, object_id)
            entity_availability_topic = self._get_entity_availability_topic(device.object_id, entity_id)

            config: dict[str, Any] = {
                "name": entity_config.get("name", entity_id),
                "unique_id": object_id,
                "device": device_info,
                "state_topic": state_topic,
                "availability": availability
                or self._build_device_availability_list(device.object_id, entity_availability_topic),
            }

            for key, value in entity_config.items():
                if key in {"component", "platform"}:
                    continue
                config[key] = value

            config["unique_id"] = object_id
            config["device"] = device_info
            config["state_topic"] = state_topic
            config["availability"] = availability or self._build_device_availability_list(
                device.object_id,
                entity_availability_topic,
            )

            self.mqtt.publish_ha_discovery(
                component=component,
                object_id=object_id,
                config=config,
                discovery_prefix=self.discovery_prefix,
            )
            self.mqtt.publish_entity_availability(device.object_id, entity_id, "online")
            self._published_entities.add(f"{component}/{object_id}")
            published_entities.append(
                PublishedDeviceEntity(
                    discovery_object_id=object_id,
                    component=component,
                    entity_key=entity_id,
                    discovery_topic=discovery_topic,
                    entity_availability_topic=entity_availability_topic,
                    config=config,
                )
            )
        return published_entities

    def _publish_generic_entities(
        self,
        device: Device,
        device_info: dict[str, Any],
        state_topic: str,
        availability: list[dict[str, str]],
    ) -> list[PublishedDeviceEntity]:
        """Publish generic entities based on M-Bus data records."""
        if not device.mbus_data:
            logger.warning(f"No M-Bus data for device ID {device.address} ({device.name})")
            return []

        published_entities: list[PublishedDeviceEntity] = []
        for record_key, record in device.mbus_data.data_records.items():
            if record.value is None:
                continue

            entity_key = f"record_{record_key}" if record_key else f"func_{record.function}"
            object_id = f"{APP_NAME}_{device.object_id}_{entity_key}"
            discovery_topic = self._get_discovery_topic("sensor", object_id)
            entity_availability_topic = self._get_entity_availability_topic(device.object_id, entity_key)

            config: dict[str, Any] = {
                "name": record.function or f"Record {record_key}",
                "unique_id": object_id,
                "device": device_info,
                "state_topic": state_topic,
                "value_template": f"{{{{ value_json.records['{record_key}'].value }}}}",
                "availability": availability
                or self._build_device_availability_list(device.object_id, entity_availability_topic),
            }

            if record.unit:
                config["unit_of_measurement"] = record.unit

            self.mqtt.publish_ha_discovery(
                component="sensor",
                object_id=object_id,
                config=config,
                discovery_prefix=self.discovery_prefix,
            )
            self.mqtt.publish_entity_availability(device.object_id, entity_key, "online")
            self._published_entities.add(f"sensor/{object_id}")
            published_entities.append(
                PublishedDeviceEntity(
                    discovery_object_id=object_id,
                    component="sensor",
                    entity_key=entity_key,
                    discovery_topic=discovery_topic,
                    entity_availability_topic=entity_availability_topic,
                    config=config,
                )
            )
        return published_entities

    def publish_replaced_device(self, identity_key: str, replaced_name: str) -> None:
        """Republish stored discovery for a replaced device with a renamed device label."""
        if self.state_store is None:
            return

        for entity in self.state_store.list_published_entities(
            identity_key,
            lifecycle_states=("active", "replaced"),
        ):
            config = copy.deepcopy(entity.config)
            device_info = config.get("device")
            if isinstance(device_info, dict):
                device_info["name"] = replaced_name
            self.mqtt.publish(entity.discovery_topic, config, retain=True)
            self.state_store.upsert_published_entity(
                discovery_object_id=entity.discovery_object_id,
                identity_key=entity.identity_key,
                component=entity.component,
                entity_key=entity.entity_key,
                discovery_topic=entity.discovery_topic,
                entity_availability_topic=entity.entity_availability_topic,
                config=config,
                lifecycle_state="replaced",
                frozen=True,
            )
            self._published_entities.add(f"{entity.component}/{entity.discovery_object_id}")

    def _resolve_device_template(self, device: Device) -> TemplateSelection:
        """Resolve the template selection for a device."""
        selection = resolve_template(
            manufacturer=device.manufacturer,
            product_name=device.model,
            data_record_count=device.datarecord_count or None,
            explicit_filename=device.template_name,
        )
        if selection.template:
            logger.debug(
                "Using template %s from %s for %s/%s (DataRecordCount=%s)",
                selection.filename,
                selection.source,
                device.manufacturer,
                device.model,
                device.datarecord_count,
            )
        return selection

    def _sync_published_entities(
        self,
        device: Device,
        published_entities: list[PublishedDeviceEntity],
    ) -> None:
        """Persist active discovery rows and retire obsolete ones."""
        if self.state_store is None or device.identity_key is None:
            return

        existing_entities = {
            entity.entity_key: entity
            for entity in self.state_store.list_published_entities(device.identity_key)
        }
        active_keys = {entity.entity_key for entity in published_entities}

        for published_entity in published_entities:
            stored_entity = existing_entities.get(published_entity.entity_key)
            if (
                stored_entity is not None
                and stored_entity.discovery_topic != published_entity.discovery_topic
            ):
                self._remove_discovery_topic(stored_entity.discovery_topic)
                self._published_entities.discard(
                    f"{stored_entity.component}/{stored_entity.discovery_object_id}"
                )
            self.state_store.upsert_published_entity(
                discovery_object_id=published_entity.discovery_object_id,
                identity_key=device.identity_key,
                component=published_entity.component,
                entity_key=published_entity.entity_key,
                discovery_topic=published_entity.discovery_topic,
                entity_availability_topic=published_entity.entity_availability_topic,
                config=published_entity.config,
                lifecycle_state="active",
                frozen=False,
            )

        for entity_key, stored_entity in existing_entities.items():
            if entity_key in active_keys:
                continue
            if stored_entity.entity_availability_topic:
                self.mqtt.publish(stored_entity.entity_availability_topic, "offline", retain=True)
            self.state_store.mark_entity_retired(device.identity_key, entity_key)

    def _remove_discovery_topic(self, discovery_topic: str) -> None:
        """Clear a retained discovery topic that no longer applies."""
        self.mqtt.publish(discovery_topic, "", retain=True)

    def _get_discovery_topic(self, component: str, object_id: str) -> str:
        """Build the retained discovery topic for an entity."""
        return f"{self.discovery_prefix}/{component}/{object_id}/config"

    def _get_entity_availability_topic(self, device_id: str, entity_key: str) -> str:
        """Build the retained entity availability topic for an entity."""
        return TOPIC_DEVICE_ENTITY_AVAILABILITY.format(
            base=self.base_topic,
            device_id=device_id,
            entity_key=entity_key,
        )

    def _build_device_availability_list(
        self,
        device_id: str,
        entity_availability_topic: str | None = None,
    ) -> list[dict[str, str]]:
        """Build HA availability list combining bridge, device, and entity availability."""
        availability = [
            {
                "topic": TOPIC_BRIDGE_STATE.format(base=self.base_topic),
                "payload_available": "online",
                "payload_not_available": "offline",
            },
            {
                "topic": TOPIC_DEVICE_AVAILABILITY.format(base=self.base_topic, device_id=device_id),
                "payload_available": "online",
                "payload_not_available": "offline",
            },
        ]
        if entity_availability_topic is not None:
            availability.append(
                {
                    "topic": entity_availability_topic,
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
            )
        return availability

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
