"""Shared pytest fixtures for libmbus2mqtt tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libmbus2mqtt.config import (
    AppConfig,
    AvailabilityConfig,
    DeviceConfig,
    HomeAssistantConfig,
    LogsConfig,
    MbusConfig,
    MqttConfig,
    PollingConfig,
)
from libmbus2mqtt.mbus.parser import parse_xml
from libmbus2mqtt.models.device import Device
from libmbus2mqtt.models.mbus import MbusData

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ============================================================================
# XML Fixture Loading
# ============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def apator_xml() -> str:
    """Load Apator APT-MBUS-NA-1 XML fixture."""
    return (FIXTURES_DIR / "apator_apt-mbus-na-1.xml").read_text()


@pytest.fixture
def itron_xml() -> str:
    """Load Itron Cyble XML fixture."""
    return (FIXTURES_DIR / "itron_cyble.xml").read_text()


@pytest.fixture
def kamstrup_xml() -> str:
    """Load Kamstrup Multical 401 XML fixture."""
    return (FIXTURES_DIR / "kamstrup_multical_401.xml").read_text()


@pytest.fixture
def bmeters_xml() -> str:
    """Load B Meters FRM-MB1 (ZRI) XML fixture."""
    return (FIXTURES_DIR / "bmeters_frm_mb1.xml").read_text()


@pytest.fixture
def zenner_xml() -> str:
    """Load Zenner EDC (ZRI) XML fixture."""
    return (FIXTURES_DIR / "zenner_edc.xml").read_text()


@pytest.fixture(
    params=[
        ("apator", "apator_apt-mbus-na-1.xml"),
        ("itron", "itron_cyble.xml"),
        ("kamstrup", "kamstrup_multical_401.xml"),
        ("bmeters", "bmeters_frm_mb1.xml"),
        ("zenner", "zenner_edc.xml"),
    ]
)
def all_xml_fixtures(request: pytest.FixtureRequest) -> tuple[str, str]:
    """Parametrized fixture yielding all XML fixtures with their names."""
    name, filename = request.param
    content = (FIXTURES_DIR / filename).read_text()
    return name, content


# ============================================================================
# Parsed MbusData Fixtures
# ============================================================================


@pytest.fixture
def apator_mbus_data(apator_xml: str) -> MbusData:
    """Parsed MbusData from Apator fixture."""
    return parse_xml(apator_xml)


@pytest.fixture
def itron_mbus_data(itron_xml: str) -> MbusData:
    """Parsed MbusData from Itron fixture."""
    return parse_xml(itron_xml)


@pytest.fixture
def kamstrup_mbus_data(kamstrup_xml: str) -> MbusData:
    """Parsed MbusData from Kamstrup fixture."""
    return parse_xml(kamstrup_xml)


@pytest.fixture
def bmeters_mbus_data(bmeters_xml: str) -> MbusData:
    """Parsed MbusData from B Meters fixture."""
    return parse_xml(bmeters_xml)


@pytest.fixture
def zenner_mbus_data(zenner_xml: str) -> MbusData:
    """Parsed MbusData from Zenner fixture."""
    return parse_xml(zenner_xml)


# ============================================================================
# Configuration Fixtures
# ============================================================================


@pytest.fixture
def minimal_mbus_config() -> MbusConfig:
    """Minimal valid M-Bus configuration."""
    return MbusConfig(device="/dev/ttyUSB0")


@pytest.fixture
def minimal_mqtt_config() -> MqttConfig:
    """Minimal valid MQTT configuration."""
    return MqttConfig(host="localhost")


@pytest.fixture
def minimal_app_config(
    minimal_mbus_config: MbusConfig,
    minimal_mqtt_config: MqttConfig,
) -> AppConfig:
    """Minimal valid application configuration."""
    return AppConfig(
        mbus=minimal_mbus_config,
        mqtt=minimal_mqtt_config,
    )


@pytest.fixture
def full_app_config() -> AppConfig:
    """Fully populated application configuration."""
    return AppConfig(
        mbus=MbusConfig(
            device="/dev/ttyUSB0",
            baudrate=2400,
            timeout=5,
            retry_count=3,
            retry_delay=1,
            autoscan=True,
        ),
        mqtt=MqttConfig(
            host="mqtt.example.com",
            port=1883,
            username="user",
            password="pass",
            client_id="test-client",
            keepalive=60,
            qos=1,
            base_topic="libmbus2mqtt",
        ),
        homeassistant=HomeAssistantConfig(
            enabled=True,
            discovery_prefix="homeassistant",
        ),
        polling=PollingConfig(interval=60, startup_delay=5),
        devices=[
            DeviceConfig(id=1, name="Water Meter", enabled=True),
            DeviceConfig(id=2, name="Heat Meter", enabled=False),
        ],
        availability=AvailabilityConfig(timeout_polls=3),
        logs=LogsConfig(level="INFO"),
    )


# ============================================================================
# Device Fixtures
# ============================================================================


@pytest.fixture
def basic_device() -> Device:
    """Basic device without M-Bus data."""
    return Device(address=1, name="Test Device")


@pytest.fixture
def device_with_mbus_data(apator_mbus_data: MbusData) -> Device:
    """Device with M-Bus data populated."""
    device = Device(address=1, name="Apator Water Meter")
    device.update_from_mbus_data(apator_mbus_data)
    return device


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_mqtt_client() -> MagicMock:
    """Mock MQTT client for testing."""
    client = MagicMock()
    client.base_topic = "libmbus2mqtt"
    client.is_connected = True
    client.publish.return_value = True
    client.publish_ha_discovery.return_value = True
    client.publish_device_state.return_value = True
    client.publish_device_availability.return_value = True
    client.remove_ha_discovery.return_value = True
    return client


@pytest.fixture
def mock_subprocess(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock subprocess.run for M-Bus interface tests."""
    mock_run = MagicMock()
    monkeypatch.setattr("subprocess.run", mock_run)
    return mock_run
