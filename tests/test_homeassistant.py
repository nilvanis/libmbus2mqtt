"""Tests for Home Assistant MQTT Discovery integration."""

from __future__ import annotations

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
