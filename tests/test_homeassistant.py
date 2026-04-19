"""Tests for Home Assistant MQTT Discovery integration."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from libmbus2mqtt.config import HomeAssistantConfig
from libmbus2mqtt.constants import APP_NAME, APP_VERSION, HA_DEFAULT_DISCOVERY_PREFIX
from libmbus2mqtt.models.device import Device
from libmbus2mqtt.models.mbus import MbusData
from libmbus2mqtt.mqtt.homeassistant import (
    BRIDGE_DEVICE_ID,
    HomeAssistantDiscovery,
    get_bridge_device_info,
    get_mbus_device_info,
)
from libmbus2mqtt.state import StateStore, build_identity_key

# ============================================================================
# Helper Function Tests
# ============================================================================


class TestGetBridgeDeviceInfo:
    """Tests for get_bridge_device_info function."""

    def test_returns_correct_structure(self) -> None:
        """Test bridge device info has correct structure."""
        info = get_bridge_device_info()

        assert "identifiers" in info
        assert "name" in info
        assert "manufacturer" in info
        assert "model" in info
        assert "sw_version" in info

    def test_identifiers_contains_bridge_id(self) -> None:
        """Test identifiers contains bridge device ID."""
        info = get_bridge_device_info()
        assert BRIDGE_DEVICE_ID in info["identifiers"]

    def test_name_contains_app_name(self) -> None:
        """Test name contains app name."""
        info = get_bridge_device_info()
        assert APP_NAME in info["name"]

    def test_sw_version_is_app_version(self) -> None:
        """Test sw_version is app version."""
        info = get_bridge_device_info()
        assert info["sw_version"] == APP_VERSION


class TestGetMbusDeviceInfo:
    """Tests for get_mbus_device_info function."""

    def test_basic_device(self) -> None:
        """Test device info for basic device."""
        device = Device(address=1)
        info = get_mbus_device_info(device)

        assert "identifiers" in info
        assert "name" in info
        assert "via_device" in info
        assert info["via_device"] == BRIDGE_DEVICE_ID

    def test_device_with_manufacturer(self, apator_mbus_data: MbusData) -> None:
        """Test device info includes manufacturer."""
        device = Device(address=1)
        device.update_from_mbus_data(apator_mbus_data)
        info = get_mbus_device_info(device)

        assert "manufacturer" in info
        assert info["manufacturer"] == "APA"

    def test_device_with_serial_number(self, apator_mbus_data: MbusData) -> None:
        """Test device info includes serial number."""
        device = Device(address=1)
        device.update_from_mbus_data(apator_mbus_data)
        info = get_mbus_device_info(device)

        assert "serial_number" in info
        assert info["serial_number"] == "67434"

    def test_device_with_model(self, itron_mbus_data: MbusData) -> None:
        """Test device info includes model."""
        device = Device(address=1)
        device.update_from_mbus_data(itron_mbus_data)
        info = get_mbus_device_info(device)

        assert "model" in info
        assert info["model"] == "Itron CYBLE M-Bus 1.4"

    def test_device_identifier_format(self) -> None:
        """Test device identifier format."""
        device = Device(address=5)
        device.serial_number = "12345"
        info = get_mbus_device_info(device)

        # Identifier should be app_name_object_id
        expected_id = f"{APP_NAME}_{device.object_id}"
        assert expected_id in info["identifiers"]


# ============================================================================
# HomeAssistantDiscovery Tests
# ============================================================================


class TestHomeAssistantDiscovery:
    """Tests for HomeAssistantDiscovery class."""

    @pytest.fixture
    def ha_config_enabled(self) -> HomeAssistantConfig:
        """Home Assistant config with discovery enabled."""
        return HomeAssistantConfig(enabled=True)

    @pytest.fixture
    def ha_config_disabled(self) -> HomeAssistantConfig:
        """Home Assistant config with discovery disabled."""
        return HomeAssistantConfig(enabled=False)

    @pytest.fixture
    def ha_config_custom_prefix(self) -> HomeAssistantConfig:
        """Home Assistant config with custom discovery prefix."""
        return HomeAssistantConfig(enabled=True, discovery_prefix="custom_prefix")

    @pytest.fixture
    def discovery(
        self,
        mock_mqtt_client: MagicMock,
        ha_config_enabled: HomeAssistantConfig,
    ) -> HomeAssistantDiscovery:
        """Create HomeAssistantDiscovery instance."""
        return HomeAssistantDiscovery(mock_mqtt_client, ha_config_enabled)

    def test_discovery_prefix_default(
        self,
        mock_mqtt_client: MagicMock,
        ha_config_enabled: HomeAssistantConfig,
    ) -> None:
        """Test default discovery prefix."""
        discovery = HomeAssistantDiscovery(mock_mqtt_client, ha_config_enabled)
        assert discovery.discovery_prefix == HA_DEFAULT_DISCOVERY_PREFIX

    def test_discovery_prefix_custom(
        self,
        mock_mqtt_client: MagicMock,
        ha_config_custom_prefix: HomeAssistantConfig,
    ) -> None:
        """Test custom discovery prefix."""
        discovery = HomeAssistantDiscovery(mock_mqtt_client, ha_config_custom_prefix)
        assert discovery.discovery_prefix == "custom_prefix"

    def test_base_topic_from_mqtt_client(
        self,
        mock_mqtt_client: MagicMock,
        ha_config_enabled: HomeAssistantConfig,
    ) -> None:
        """Test base topic comes from MQTT client."""
        discovery = HomeAssistantDiscovery(mock_mqtt_client, ha_config_enabled)
        assert discovery.base_topic == mock_mqtt_client.base_topic


class TestPublishBridgeDiscovery:
    """Tests for publish_bridge_discovery method."""

    @pytest.fixture
    def discovery(
        self,
        mock_mqtt_client: MagicMock,
    ) -> HomeAssistantDiscovery:
        """Create HomeAssistantDiscovery instance."""
        config = HomeAssistantConfig(enabled=True)
        return HomeAssistantDiscovery(mock_mqtt_client, config)

    @pytest.fixture
    def discovery_disabled(
        self,
        mock_mqtt_client: MagicMock,
    ) -> HomeAssistantDiscovery:
        """Create HomeAssistantDiscovery instance with HA disabled."""
        config = HomeAssistantConfig(enabled=False)
        return HomeAssistantDiscovery(mock_mqtt_client, config)

    def test_publishes_bridge_sensors(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test bridge sensors are published."""
        discovery.publish_bridge_discovery()

        # Check publish_ha_discovery was called for sensors
        calls = mock_mqtt_client.publish_ha_discovery.call_args_list

        # Should have multiple calls for different entities
        assert len(calls) > 0

        # Check for specific sensors
        object_ids = [
            c.kwargs.get("object_id", c.args[1] if len(c.args) > 1 else None) for c in calls
        ]
        expected_sensors = [
            f"{BRIDGE_DEVICE_ID}_discovered_devices",
            f"{BRIDGE_DEVICE_ID}_online_devices",
            f"{BRIDGE_DEVICE_ID}_version",
        ]
        for sensor in expected_sensors:
            assert any(sensor in str(oid) for oid in object_ids)

    def test_publishes_bridge_button(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test rescan button is published."""
        discovery.publish_bridge_discovery()

        calls = mock_mqtt_client.publish_ha_discovery.call_args_list

        # Find button call
        button_calls = [c for c in calls if c.kwargs.get("component") == "button"]
        assert len(button_calls) > 0

    def test_publishes_bridge_select(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test log level select is published."""
        discovery.publish_bridge_discovery()

        calls = mock_mqtt_client.publish_ha_discovery.call_args_list

        # Find select call
        select_calls = [c for c in calls if c.kwargs.get("component") == "select"]
        assert len(select_calls) > 0

    def test_publishes_bridge_number(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test poll interval number is published."""
        discovery.publish_bridge_discovery()

        calls = mock_mqtt_client.publish_ha_discovery.call_args_list

        # Find number call
        number_calls = [c for c in calls if c.kwargs.get("component") == "number"]
        assert len(number_calls) > 0

    def test_last_scan_sensor_uses_timestamp_device_class(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test Last Scan sensor is published as a timestamp sensor."""
        discovery.publish_bridge_discovery()

        last_scan_call = next(
            call
            for call in mock_mqtt_client.publish_ha_discovery.call_args_list
            if call.kwargs.get("object_id") == f"{BRIDGE_DEVICE_ID}_last_scan"
        )

        config = last_scan_call.kwargs["config"]
        assert config["device_class"] == "timestamp"
        assert config["value_template"] == "{{ value_json.get('last_scan') }}"

    def test_last_poll_duration_sensor_uses_safe_template(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test Last Poll Duration sensor tolerates missing keys."""
        discovery.publish_bridge_discovery()

        duration_call = next(
            call
            for call in mock_mqtt_client.publish_ha_discovery.call_args_list
            if call.kwargs.get("object_id") == f"{BRIDGE_DEVICE_ID}_last_poll_duration"
        )

        config = duration_call.kwargs["config"]
        assert config["value_template"] == "{{ value_json.get('last_poll_duration_ms') }}"

    def test_disabled_does_not_publish(
        self,
        discovery_disabled: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test disabled config does not publish."""
        discovery_disabled.publish_bridge_discovery()
        mock_mqtt_client.publish_ha_discovery.assert_not_called()


class TestPublishDeviceDiscovery:
    """Tests for publish_device_discovery method."""

    @pytest.fixture
    def discovery(
        self,
        mock_mqtt_client: MagicMock,
    ) -> HomeAssistantDiscovery:
        """Create HomeAssistantDiscovery instance."""
        config = HomeAssistantConfig(enabled=True)
        return HomeAssistantDiscovery(mock_mqtt_client, config)

    @pytest.fixture
    def discovery_disabled(
        self,
        mock_mqtt_client: MagicMock,
    ) -> HomeAssistantDiscovery:
        """Create HomeAssistantDiscovery instance with HA disabled."""
        config = HomeAssistantConfig(enabled=False)
        return HomeAssistantDiscovery(mock_mqtt_client, config)

    def test_publishes_device_with_template(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
        itron_mbus_data: MbusData,
    ) -> None:
        """Test device with template publishes template entities."""
        device = Device(address=1)
        device.update_from_mbus_data(itron_mbus_data)

        discovery.publish_device_discovery(device)

        # Should have called publish_ha_discovery
        assert mock_mqtt_client.publish_ha_discovery.called

        # Device should be marked as published
        assert device.ha_discovery_published is True

    def test_publishes_device_generic_entities(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test device without template publishes generic entities."""
        device = Device(address=1)
        device.manufacturer = "UNKNOWN"  # No template for this

        # Create minimal mbus_data manually
        from libmbus2mqtt.models.mbus import DataRecord, MbusData, SlaveInformation

        mbus_data = MbusData(
            slave_information=SlaveInformation(
                Id="123",
                Manufacturer="UNKNOWN",
                Version="1",
                Medium="Water",
            ),
            data_records={
                "0": DataRecord(
                    id="0",
                    Function="Volume",
                    Unit="m^3",
                    Value="12345",
                )
            },
        )
        device.mbus_data = mbus_data

        discovery.publish_device_discovery(device)

        # Should have called publish_ha_discovery
        assert mock_mqtt_client.publish_ha_discovery.called
        assert device.ha_discovery_published is True

    def test_disabled_does_not_publish(
        self,
        discovery_disabled: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
        itron_mbus_data: MbusData,
    ) -> None:
        """Test disabled config does not publish."""
        device = Device(address=1)
        device.update_from_mbus_data(itron_mbus_data)

        discovery_disabled.publish_device_discovery(device)

        mock_mqtt_client.publish_ha_discovery.assert_not_called()
        assert device.ha_discovery_published is False

    def test_template_fields_passthrough(
        self,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Template-defined discovery fields should be passed through."""
        discovery = HomeAssistantDiscovery(mock_mqtt_client, HomeAssistantConfig(enabled=True))
        device = Device(address=1)
        device_info = get_mbus_device_info(device)
        template = {
            "custom": {
                "component": "sensor",
                "name": "Custom Sensor",
                "value_template": "{{ value_json.custom }}",
                "entity_category": "diagnostic",
                "enabled_by_default": False,
                "suggested_display_precision": 2,
                "icon": "mdi:test-tube",
            }
        }

        discovery._publish_template_entities(
            device=device,
            device_info=device_info,
            template=template,
            state_topic="test/state",
            availability=[],
        )

        args = mock_mqtt_client.publish_ha_discovery.call_args
        cfg = args.kwargs["config"]
        assert cfg["entity_category"] == "diagnostic"
        assert cfg["enabled_by_default"] is False
        assert cfg["suggested_display_precision"] == 2
        assert cfg["icon"] == "mdi:test-tube"


class TestPersistentDiscoveryState:
    """Tests for persisted discovery entity lifecycle."""

    @pytest.fixture
    def state_store(self, tmp_path_factory: pytest.TempPathFactory) -> StateStore:
        """Create temporary SQLite state store."""
        return StateStore(tmp_path_factory.mktemp("state") / "libmbus2mqtt.db")

    @pytest.fixture
    def discovery_with_state(
        self,
        mock_mqtt_client: MagicMock,
        state_store: StateStore,
    ) -> HomeAssistantDiscovery:
        """Create HomeAssistantDiscovery with persistent state."""
        return HomeAssistantDiscovery(
            mock_mqtt_client,
            HomeAssistantConfig(enabled=True),
            state_store,
        )

    def test_publish_replaced_device_renames_stored_discovery(
        self,
        discovery_with_state: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Stored discovery should be republished with replaced device name."""
        identity_key = build_identity_key("123", "ACW", "Meter")
        state_store.upsert_identity(
            identity_key=identity_key,
            object_id="123",
            manufacturer="ACW",
            model="Meter",
            status="active",
            last_address=1,
            increment_activation=True,
        )
        state_store.upsert_published_entity(
            discovery_object_id="libmbus2mqtt_123_0",
            identity_key=identity_key,
            component="sensor",
            entity_key="0",
            discovery_topic="homeassistant/sensor/libmbus2mqtt_123_0/config",
            entity_availability_topic="libmbus2mqtt/device/123/entity/0/availability",
            config={
                "name": "Fabrication Number",
                "device": {"name": "Water Meter"},
            },
            lifecycle_state="active",
            frozen=False,
        )

        discovery_with_state.publish_replaced_device(identity_key, "Water Meter (replaced)")

        publish_calls = mock_mqtt_client.publish.call_args_list
        assert publish_calls
        assert publish_calls[0].args[0] == "homeassistant/sensor/libmbus2mqtt_123_0/config"
        assert publish_calls[0].kwargs["retain"] is True
        assert publish_calls[0].args[1]["device"]["name"] == "Water Meter (replaced)"

        entity = state_store.list_published_entities(identity_key)[0]
        assert entity.lifecycle_state == "replaced"
        assert entity.frozen is True

    def test_publish_replaced_device_skips_retired_entities(
        self,
        discovery_with_state: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Replacing a device should not resurrect entities already retired by rematch."""
        identity_key = build_identity_key("123", "ACW", "Meter")
        state_store.upsert_identity(
            identity_key=identity_key,
            object_id="123",
            manufacturer="ACW",
            model="Meter",
            status="active",
            last_address=1,
            increment_activation=True,
        )
        state_store.upsert_published_entity(
            discovery_object_id="libmbus2mqtt_123_0",
            identity_key=identity_key,
            component="sensor",
            entity_key="0",
            discovery_topic="homeassistant/sensor/libmbus2mqtt_123_0/config",
            entity_availability_topic="libmbus2mqtt/device/123/entity/0/availability",
            config={"name": "Active", "device": {"name": "Water Meter"}},
            lifecycle_state="active",
            frozen=False,
        )
        state_store.upsert_published_entity(
            discovery_object_id="libmbus2mqtt_123_7",
            identity_key=identity_key,
            component="sensor",
            entity_key="7",
            discovery_topic="homeassistant/sensor/libmbus2mqtt_123_7/config",
            entity_availability_topic="libmbus2mqtt/device/123/entity/7/availability",
            config={"name": "Retired", "device": {"name": "Water Meter"}},
            lifecycle_state="retired",
            frozen=True,
        )
        state_store.mark_entities_replaced(identity_key)

        discovery_with_state.publish_replaced_device(identity_key, "Water Meter (replaced)")

        publish_topics = [call.args[0] for call in mock_mqtt_client.publish.call_args_list]
        assert "homeassistant/sensor/libmbus2mqtt_123_0/config" in publish_topics
        assert "homeassistant/sensor/libmbus2mqtt_123_7/config" not in publish_topics

        entities = {
            entity.entity_key: entity
            for entity in state_store.list_published_entities(identity_key)
        }
        assert entities["0"].lifecycle_state == "replaced"
        assert entities["7"].lifecycle_state == "retired"

    def test_restore_active_device_discovery_republishes_active_entities(
        self,
        discovery_with_state: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Restore should republish active retained discovery and entity availability only."""
        identity_key = build_identity_key("123", "ACW", "Meter")
        state_store.upsert_identity(
            identity_key=identity_key,
            object_id="123",
            manufacturer="ACW",
            model="Meter",
            status="active",
            last_address=1,
            increment_activation=True,
        )
        state_store.upsert_published_entity(
            discovery_object_id="libmbus2mqtt_123_0",
            identity_key=identity_key,
            component="sensor",
            entity_key="0",
            discovery_topic="homeassistant/sensor/libmbus2mqtt_123_0/config",
            entity_availability_topic="libmbus2mqtt/device/123/entity/0/availability",
            config={"name": "Active", "device": {"name": "Water Meter"}},
            lifecycle_state="active",
            frozen=False,
        )
        state_store.upsert_published_entity(
            discovery_object_id="libmbus2mqtt_123_7",
            identity_key=identity_key,
            component="sensor",
            entity_key="7",
            discovery_topic="homeassistant/sensor/libmbus2mqtt_123_7/config",
            entity_availability_topic="libmbus2mqtt/device/123/entity/7/availability",
            config={"name": "Retired", "device": {"name": "Water Meter"}},
            lifecycle_state="retired",
            frozen=True,
        )

        discovery_with_state.restore_active_device_discovery(identity_key)

        publish_calls = mock_mqtt_client.publish.call_args_list
        assert len(publish_calls) == 2
        assert publish_calls[0].args == ("libmbus2mqtt/device/123/entity/0/availability", "online")
        assert publish_calls[0].kwargs["retain"] is True
        assert publish_calls[1].args[0] == "homeassistant/sensor/libmbus2mqtt_123_0/config"
        assert publish_calls[1].args[1]["name"] == "Active"
        assert publish_calls[1].kwargs["retain"] is True

    def test_template_rematch_retires_removed_entities(
        self,
        discovery_with_state: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
        state_store: StateStore,
        itron_mbus_data: MbusData,
        itron_dr7_mbus_data: MbusData,
    ) -> None:
        """Entities removed by rematch should be retired and marked offline."""
        device = Device(address=1)
        device.update_from_mbus_data(itron_mbus_data)
        identity_key = build_identity_key(
            device.object_id,
            device.manufacturer or "",
            device.model or "",
        )
        state_store.upsert_identity(
            identity_key=identity_key,
            object_id=device.object_id,
            manufacturer=device.manufacturer or "",
            model=device.model or "",
            status="active",
            last_address=device.address,
            increment_activation=True,
        )
        device.identity_key = identity_key

        discovery_with_state.publish_device_discovery(device)

        rematch_data = deepcopy(itron_dr7_mbus_data)
        rematch_data.slave_information.id = itron_mbus_data.device_id
        device.update_from_mbus_data(rematch_data)
        device.identity_key = identity_key

        mock_mqtt_client.reset_mock()
        discovery_with_state.publish_device_discovery(device)

        entities = {
            entity.entity_key: entity
            for entity in state_store.list_published_entities(identity_key)
        }
        assert entities["7"].lifecycle_state == "retired"
        assert entities["7"].frozen is True
        assert entities["6"].lifecycle_state == "active"

        offline_topic = f"libmbus2mqtt/device/{itron_mbus_data.device_id}/entity/7/availability"
        assert any(
            call.args == (offline_topic, "offline") and call.kwargs.get("retain") is True
            for call in mock_mqtt_client.publish.call_args_list
        )

    def test_retired_entity_reactivates_without_duplicate_row(
        self,
        discovery_with_state: HomeAssistantDiscovery,
        state_store: StateStore,
        itron_mbus_data: MbusData,
        itron_dr7_mbus_data: MbusData,
    ) -> None:
        """A later rematch should reactivate the same stored entity row."""
        device = Device(address=1)
        device.update_from_mbus_data(itron_mbus_data)
        identity_key = build_identity_key(
            device.object_id,
            device.manufacturer or "",
            device.model or "",
        )
        state_store.upsert_identity(
            identity_key=identity_key,
            object_id=device.object_id,
            manufacturer=device.manufacturer or "",
            model=device.model or "",
            status="active",
            last_address=device.address,
            increment_activation=True,
        )
        device.identity_key = identity_key

        discovery_with_state.publish_device_discovery(device)

        rematch_data = deepcopy(itron_dr7_mbus_data)
        rematch_data.slave_information.id = itron_mbus_data.device_id
        device.update_from_mbus_data(rematch_data)
        device.identity_key = identity_key
        discovery_with_state.publish_device_discovery(device)

        device.update_from_mbus_data(itron_mbus_data)
        device.identity_key = identity_key
        discovery_with_state.publish_device_discovery(device)

        entities = [
            entity
            for entity in state_store.list_published_entities(identity_key)
            if entity.entity_key == "7"
        ]
        assert len(entities) == 1
        assert entities[0].lifecycle_state == "active"
        assert entities[0].frozen is False

    def test_component_change_removes_old_discovery_topic(
        self,
        discovery_with_state: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Changing component for the same entity key should clear the old retained topic."""
        device = Device(address=1)
        device.serial_number = "123"
        device.manufacturer = "ACW"
        device.model = "Meter"
        device.identity_key = build_identity_key("123", "ACW", "Meter")
        state_store.upsert_identity(
            identity_key=device.identity_key,
            object_id=device.object_id,
            manufacturer=device.manufacturer,
            model=device.model,
            status="active",
            last_address=device.address,
            increment_activation=True,
        )
        device_info = get_mbus_device_info(device)
        sensor_entities = discovery_with_state._publish_template_entities(
            device=device,
            device_info=device_info,
            template={
                "flag": {
                    "component": "sensor",
                    "name": "Flag",
                    "value_template": "{{ value_json.flag }}",
                }
            },
            state_topic="libmbus2mqtt/device/123/state",
            availability=[],
        )
        discovery_with_state._sync_published_entities(device, sensor_entities)

        mock_mqtt_client.reset_mock()
        binary_sensor_entities = discovery_with_state._publish_template_entities(
            device=device,
            device_info=device_info,
            template={
                "flag": {
                    "component": "binary_sensor",
                    "name": "Flag",
                    "value_template": "{{ value_json.flag }}",
                }
            },
            state_topic="libmbus2mqtt/device/123/state",
            availability=[],
        )
        discovery_with_state._sync_published_entities(device, binary_sensor_entities)

        assert any(
            call.args == ("homeassistant/sensor/libmbus2mqtt_123_flag/config", "")
            and call.kwargs.get("retain") is True
            for call in mock_mqtt_client.publish.call_args_list
        )


class TestRemoveAllDiscovery:
    """Tests for remove_all_discovery method."""

    @pytest.fixture
    def discovery(
        self,
        mock_mqtt_client: MagicMock,
    ) -> HomeAssistantDiscovery:
        """Create HomeAssistantDiscovery instance."""
        config = HomeAssistantConfig(enabled=True)
        return HomeAssistantDiscovery(mock_mqtt_client, config)

    def test_removes_published_entities(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test removes all published entities."""
        # First publish some entities
        discovery.publish_bridge_discovery()

        # Get number of published entities
        num_published = len(discovery._published_entities)
        assert num_published > 0

        # Clear mock to count removal calls
        mock_mqtt_client.reset_mock()

        # Remove all
        discovery.remove_all_discovery()

        # Should have called remove_ha_discovery for each entity
        assert mock_mqtt_client.remove_ha_discovery.call_count == num_published

        # Published entities should be cleared
        assert len(discovery._published_entities) == 0

    def test_empty_entities_does_nothing(
        self,
        discovery: HomeAssistantDiscovery,
        mock_mqtt_client: MagicMock,
    ) -> None:
        """Test removing with no entities does nothing."""
        discovery.remove_all_discovery()
        mock_mqtt_client.remove_ha_discovery.assert_not_called()
