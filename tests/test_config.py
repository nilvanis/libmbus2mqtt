"""Tests for configuration models and loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from libmbus2mqtt.config import (
    AppConfig,
    DeviceConfig,
    LogsConfig,
    MbusConfig,
    MqttConfig,
    generate_example_config,
)


class TestMbusConfig:
    """Tests for MbusConfig model."""

    def test_minimal_config(self) -> None:
        """Test minimal required configuration."""
        config = MbusConfig(device="/dev/ttyUSB0")
        assert config.device == "/dev/ttyUSB0"
        assert config.baudrate == 2400  # default
        assert config.timeout == 5  # default
        assert config.retry_count == 3  # default
        assert config.autoscan is True  # default

    def test_valid_baudrate_300(self) -> None:
        """Test baudrate 300 is accepted."""
        config = MbusConfig(device="/dev/ttyUSB0", baudrate=300)
        assert config.baudrate == 300

    def test_valid_baudrate_2400(self) -> None:
        """Test baudrate 2400 is accepted."""
        config = MbusConfig(device="/dev/ttyUSB0", baudrate=2400)
        assert config.baudrate == 2400

    def test_valid_baudrate_9600(self) -> None:
        """Test baudrate 9600 is accepted."""
        config = MbusConfig(device="/dev/ttyUSB0", baudrate=9600)
        assert config.baudrate == 9600

    def test_invalid_baudrate_1200(self) -> None:
        """Test baudrate 1200 raises ValueError."""
        with pytest.raises(ValidationError, match="Baudrate must be one of"):
            MbusConfig(device="/dev/ttyUSB0", baudrate=1200)

    def test_invalid_baudrate_4800(self) -> None:
        """Test baudrate 4800 raises ValueError."""
        with pytest.raises(ValidationError, match="Baudrate must be one of"):
            MbusConfig(device="/dev/ttyUSB0", baudrate=4800)

    def test_invalid_baudrate_19200(self) -> None:
        """Test baudrate 19200 raises ValueError."""
        with pytest.raises(ValidationError, match="Baudrate must be one of"):
            MbusConfig(device="/dev/ttyUSB0", baudrate=19200)

    def test_tcp_device_allows_any_baudrate(self) -> None:
        """Baudrate is ignored for TCP endpoints."""
        config = MbusConfig(device="192.168.1.10:10001", baudrate=19200)
        assert config.device == "192.168.1.10:10001"
        assert config.baudrate == 19200

    def test_tcp_device_must_be_valid_ipv4(self) -> None:
        """Invalid IPv4 address raises ValueError."""
        with pytest.raises(ValidationError):
            MbusConfig(device="999.1.1.1:1000")

    def test_tcp_device_port_range(self) -> None:
        """Port must be within valid range."""
        with pytest.raises(ValidationError):
            MbusConfig(device="192.168.1.10:70000")

    def test_tcp_device_hostname_not_allowed(self) -> None:
        """Hostnames are not supported for TCP mode."""
        with pytest.raises(ValidationError):
            MbusConfig(device="example.com:1000")

    def test_timeout_must_be_ge_1(self) -> None:
        """Test timeout must be >= 1."""
        with pytest.raises(ValidationError):
            MbusConfig(device="/dev/ttyUSB0", timeout=0)

    def test_retry_count_can_be_zero(self) -> None:
        """Test retry_count can be 0."""
        config = MbusConfig(device="/dev/ttyUSB0", retry_count=0)
        assert config.retry_count == 0

    def test_retry_count_cannot_be_negative(self) -> None:
        """Test retry_count cannot be negative."""
        with pytest.raises(ValidationError):
            MbusConfig(device="/dev/ttyUSB0", retry_count=-1)


class TestMqttConfig:
    """Tests for MqttConfig model."""

    def test_minimal_config(self) -> None:
        """Test minimal required configuration."""
        config = MqttConfig(host="localhost")
        assert config.host == "localhost"
        assert config.port == 1883  # default
        assert config.username is None
        assert config.password is None
        assert config.keepalive == 60  # default
        assert config.qos == 1  # default
        assert config.base_topic == "libmbus2mqtt"  # default

    def test_client_id_auto_generated(self) -> None:
        """Test client_id is auto-generated if not provided."""
        config = MqttConfig(host="localhost")
        assert config.client_id is not None
        assert config.client_id.startswith("libmbus2mqtt-")

    def test_client_id_preserved_if_provided(self) -> None:
        """Test client_id is preserved if explicitly provided."""
        config = MqttConfig(host="localhost", client_id="my-custom-id")
        assert config.client_id == "my-custom-id"

    def test_port_too_low(self) -> None:
        """Test port 0 is invalid."""
        with pytest.raises(ValidationError):
            MqttConfig(host="localhost", port=0)

    def test_port_too_high(self) -> None:
        """Test port 65536 is invalid."""
        with pytest.raises(ValidationError):
            MqttConfig(host="localhost", port=65536)

    def test_port_8883(self) -> None:
        """Test port 8883 is valid (TLS)."""
        config = MqttConfig(host="localhost", port=8883)
        assert config.port == 8883

    def test_qos_0_valid(self) -> None:
        """Test QoS 0 is valid."""
        config = MqttConfig(host="localhost", qos=0)
        assert config.qos == 0

    def test_qos_1_valid(self) -> None:
        """Test QoS 1 is valid."""
        config = MqttConfig(host="localhost", qos=1)
        assert config.qos == 1

    def test_qos_2_valid(self) -> None:
        """Test QoS 2 is valid."""
        config = MqttConfig(host="localhost", qos=2)
        assert config.qos == 2

    def test_qos_3_invalid(self) -> None:
        """Test QoS 3 is invalid."""
        with pytest.raises(ValidationError):
            MqttConfig(host="localhost", qos=3)

    def test_qos_negative_invalid(self) -> None:
        """Test negative QoS is invalid."""
        with pytest.raises(ValidationError):
            MqttConfig(host="localhost", qos=-1)


class TestDeviceConfig:
    """Tests for DeviceConfig model."""

    def test_valid_device_config(self) -> None:
        """Test valid device configuration."""
        config = DeviceConfig(id=1, name="Water Meter")
        assert config.id == 1
        assert config.name == "Water Meter"
        assert config.enabled is True  # default
        assert config.template is None  # default

    def test_device_id_0_valid(self) -> None:
        """Test device ID 0 is valid."""
        config = DeviceConfig(id=0)
        assert config.id == 0

    def test_device_id_254_valid(self) -> None:
        """Test device ID 254 is valid."""
        config = DeviceConfig(id=254)
        assert config.id == 254

    def test_device_id_255_invalid(self) -> None:
        """Test device ID 255 is invalid."""
        with pytest.raises(ValidationError):
            DeviceConfig(id=255)

    def test_device_id_negative_invalid(self) -> None:
        """Test negative device ID is invalid."""
        with pytest.raises(ValidationError):
            DeviceConfig(id=-1)

    def test_device_id_zero_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test warning is logged for device ID 0."""
        DeviceConfig(id=0)
        assert "Device ID 0 is the default M-Bus address" in caplog.text


class TestLogsConfig:
    """Tests for LogsConfig model."""

    def test_valid_log_level_debug(self) -> None:
        """Test DEBUG log level is valid."""
        config = LogsConfig(level="DEBUG")
        assert config.level == "DEBUG"

    def test_valid_log_level_info(self) -> None:
        """Test INFO log level is valid."""
        config = LogsConfig(level="INFO")
        assert config.level == "INFO"

    def test_valid_log_level_warning(self) -> None:
        """Test WARNING log level is valid."""
        config = LogsConfig(level="WARNING")
        assert config.level == "WARNING"

    def test_valid_log_level_error(self) -> None:
        """Test ERROR log level is valid."""
        config = LogsConfig(level="ERROR")
        assert config.level == "ERROR"

    def test_valid_log_level_critical(self) -> None:
        """Test CRITICAL log level is valid."""
        config = LogsConfig(level="CRITICAL")
        assert config.level == "CRITICAL"

    def test_log_level_case_insensitive_lowercase(self) -> None:
        """Test log level is case-insensitive (lowercase)."""
        config = LogsConfig(level="debug")
        assert config.level == "DEBUG"

    def test_log_level_case_insensitive_mixed(self) -> None:
        """Test log level is case-insensitive (mixed case)."""
        config = LogsConfig(level="Info")
        assert config.level == "INFO"

    def test_invalid_log_level_trace(self) -> None:
        """Test TRACE log level is invalid."""
        with pytest.raises(ValidationError, match="Log level must be one of"):
            LogsConfig(level="TRACE")

    def test_max_size_mb_too_low(self) -> None:
        """Test max_size_mb 0 is invalid."""
        with pytest.raises(ValidationError):
            LogsConfig(max_size_mb=0)

    def test_max_size_mb_too_high(self) -> None:
        """Test max_size_mb 1001 is invalid."""
        with pytest.raises(ValidationError):
            LogsConfig(max_size_mb=1001)

    def test_backup_count_zero_valid(self) -> None:
        """Test backup_count 0 is valid."""
        config = LogsConfig(backup_count=0)
        assert config.backup_count == 0

    def test_backup_count_100_valid(self) -> None:
        """Test backup_count 100 is valid."""
        config = LogsConfig(backup_count=100)
        assert config.backup_count == 100

    def test_backup_count_negative_invalid(self) -> None:
        """Test negative backup_count is invalid."""
        with pytest.raises(ValidationError):
            LogsConfig(backup_count=-1)

    def test_backup_count_101_invalid(self) -> None:
        """Test backup_count 101 is invalid."""
        with pytest.raises(ValidationError):
            LogsConfig(backup_count=101)


class TestAppConfig:
    """Tests for AppConfig model."""

    def test_minimal_app_config(
        self,
        minimal_mbus_config: MbusConfig,
        minimal_mqtt_config: MqttConfig,
    ) -> None:
        """Test minimal application configuration."""
        config = AppConfig(
            mbus=minimal_mbus_config,
            mqtt=minimal_mqtt_config,
        )
        assert config.mbus.device == "/dev/ttyUSB0"
        assert config.mqtt.host == "localhost"
        assert config.homeassistant.enabled is False  # default
        assert config.devices == []  # default

    def test_get_device_config_found(self, full_app_config: AppConfig) -> None:
        """Test get_device_config returns device when found."""
        device = full_app_config.get_device_config(1)
        assert device is not None
        assert device.name == "Water Meter"

    def test_get_device_config_not_found(self, full_app_config: AppConfig) -> None:
        """Test get_device_config returns None when not found."""
        device = full_app_config.get_device_config(99)
        assert device is None

    def test_is_device_enabled_true(self, full_app_config: AppConfig) -> None:
        """Test is_device_enabled returns True for enabled device."""
        assert full_app_config.is_device_enabled(1) is True

    def test_is_device_enabled_false(self, full_app_config: AppConfig) -> None:
        """Test is_device_enabled returns False for disabled device."""
        assert full_app_config.is_device_enabled(2) is False

    def test_is_device_enabled_unknown(self, full_app_config: AppConfig) -> None:
        """Test is_device_enabled defaults to True for unknown device."""
        assert full_app_config.is_device_enabled(99) is True

    def test_from_yaml(self, tmp_path: Path) -> None:
        """Test loading configuration from YAML file."""
        config_yaml = """
mbus:
  device: /dev/ttyUSB0
  baudrate: 9600
mqtt:
  host: mqtt.local
  port: 1883
homeassistant:
  enabled: true
devices:
  - id: 1
    name: Test Meter
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_yaml)

        config = AppConfig.from_yaml(config_file)
        assert config.mbus.device == "/dev/ttyUSB0"
        assert config.mbus.baudrate == 9600
        assert config.mqtt.host == "mqtt.local"
        assert config.homeassistant.enabled is True
        assert len(config.devices) == 1
        assert config.devices[0].name == "Test Meter"

    def test_from_yaml_file_not_found(self) -> None:
        """Test FileNotFoundError when config file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            AppConfig.from_yaml("/nonexistent/config.yaml")

    def test_from_yaml_missing_required(self, tmp_path: Path) -> None:
        """Test loading empty YAML file fails (missing required fields)."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        with pytest.raises(ValidationError):
            AppConfig.from_yaml(config_file)


class TestGenerateExampleConfig:
    """Tests for generate_example_config function."""

    def test_generates_valid_yaml(self) -> None:
        """Test generated config is valid YAML."""
        example = generate_example_config()
        parsed = yaml.safe_load(example)
        assert "mbus" in parsed
        assert "mqtt" in parsed
        assert "homeassistant" in parsed

    def test_example_has_required_fields(self) -> None:
        """Test example contains required field placeholders."""
        example = generate_example_config()
        assert "device:" in example
        assert "host:" in example
