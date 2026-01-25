"""Configuration models using Pydantic."""

from __future__ import annotations

import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from libmbus2mqtt.constants import (
    AVAILABILITY_DEFAULT_TIMEOUT_POLLS,
    DEFAULT_CONFIG_FILE,
    ENV_PREFIX,
    HA_DEFAULT_DISCOVERY_PREFIX,
    LOG_DEFAULT_BACKUP_COUNT,
    LOG_DEFAULT_FILE,
    LOG_DEFAULT_MAX_SIZE_MB,
    LOG_LEVELS,
    MBUS_BAUDRATES,
    MBUS_DEFAULT_BAUDRATE,
    MBUS_DEFAULT_RETRY_COUNT,
    MBUS_DEFAULT_RETRY_DELAY,
    MBUS_DEFAULT_TIMEOUT,
    MBUS_ID_MAX,
    MBUS_ID_MIN,
    MQTT_DEFAULT_BASE_TOPIC,
    MQTT_DEFAULT_KEEPALIVE,
    MQTT_DEFAULT_PORT,
    MQTT_DEFAULT_QOS,
    POLLING_DEFAULT_INTERVAL,
    POLLING_DEFAULT_STARTUP_DELAY,
)
from libmbus2mqtt.mbus.utils import parse_mbus_device

EnvPath = tuple[str, ...]

ENV_VAR_PATHS: dict[str, EnvPath] = {
    # M-Bus
    f"{ENV_PREFIX}_MBUS_DEVICE": ("mbus", "device"),
    f"{ENV_PREFIX}_MBUS_BAUDRATE": ("mbus", "baudrate"),
    f"{ENV_PREFIX}_MBUS_TIMEOUT": ("mbus", "timeout"),
    f"{ENV_PREFIX}_MBUS_RETRY_COUNT": ("mbus", "retry_count"),
    f"{ENV_PREFIX}_MBUS_RETRY_DELAY": ("mbus", "retry_delay"),
    f"{ENV_PREFIX}_MBUS_AUTOSCAN": ("mbus", "autoscan"),
    # MQTT
    f"{ENV_PREFIX}_MQTT_HOST": ("mqtt", "host"),
    f"{ENV_PREFIX}_MQTT_PORT": ("mqtt", "port"),
    f"{ENV_PREFIX}_MQTT_USERNAME": ("mqtt", "username"),
    f"{ENV_PREFIX}_MQTT_PASSWORD": ("mqtt", "password"),
    f"{ENV_PREFIX}_MQTT_CLIENT_ID": ("mqtt", "client_id"),
    f"{ENV_PREFIX}_MQTT_KEEPALIVE": ("mqtt", "keepalive"),
    f"{ENV_PREFIX}_MQTT_QOS": ("mqtt", "qos"),
    f"{ENV_PREFIX}_MQTT_BASE_TOPIC": ("mqtt", "base_topic"),
    # Home Assistant
    f"{ENV_PREFIX}_HOMEASSISTANT_ENABLED": ("homeassistant", "enabled"),
    f"{ENV_PREFIX}_HOMEASSISTANT_DISCOVERY_PREFIX": ("homeassistant", "discovery_prefix"),
    # Polling
    f"{ENV_PREFIX}_POLLING_INTERVAL": ("polling", "interval"),
    f"{ENV_PREFIX}_POLLING_STARTUP_DELAY": ("polling", "startup_delay"),
    # Availability
    f"{ENV_PREFIX}_AVAILABILITY_TIMEOUT_POLLS": ("availability", "timeout_polls"),
    # Logging
    f"{ENV_PREFIX}_LOGS_LEVEL": ("logs", "level"),
    f"{ENV_PREFIX}_LOGS_SAVE_TO_FILE": ("logs", "save_to_file"),
    f"{ENV_PREFIX}_LOGS_FILE": ("logs", "file"),
    f"{ENV_PREFIX}_LOGS_MAX_SIZE_MB": ("logs", "max_size_mb"),
    f"{ENV_PREFIX}_LOGS_BACKUP_COUNT": ("logs", "backup_count"),
}


def _get_nested(data: dict[str, Any], path: EnvPath) -> tuple[bool, Any]:
    """Retrieve a nested value and whether it exists."""
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _set_nested(data: dict[str, Any], path: EnvPath, value: Any) -> None:
    """Set a nested value, creating intermediate dicts as needed."""
    current: dict[str, Any] = data
    for key in path[:-1]:
        current = current.setdefault(key, {})
    current[path[-1]] = value


def _merge_env_with_config(config_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Apply environment values only where config.yaml does not set a value.

    Emits a warning when both env and config provide the same field.
    """
    merged = deepcopy(config_dict)
    logger = logging.getLogger("libmbus2mqtt.config")

    for env_var, path in ENV_VAR_PATHS.items():
        if env_var not in os.environ:
            continue

        env_value = os.environ[env_var]
        exists, existing_value = _get_nested(merged, path)

        if exists:
            logger.warning(
                "Ignoring env %s; config file sets %s (using config value: %s)",
                env_var,
                ".".join(path),
                existing_value,
            )
            continue

        _set_nested(merged, path, env_value)

    return merged


class MbusConfig(BaseModel):
    """M-Bus interface configuration."""

    device: str = Field(
        ...,
        description="Serial/TTY device path or IPv4:port (e.g. 192.168.1.10:9999)",
    )
    baudrate: int = Field(default=MBUS_DEFAULT_BAUDRATE, description="Baud rate")
    timeout: int = Field(default=MBUS_DEFAULT_TIMEOUT, ge=1, description="Timeout in seconds")
    retry_count: int = Field(default=MBUS_DEFAULT_RETRY_COUNT, ge=0, description="Retry count")
    retry_delay: int = Field(default=MBUS_DEFAULT_RETRY_DELAY, ge=0, description="Retry delay")
    autoscan: bool = Field(default=True, description="Auto-scan for devices on startup")

    @field_validator("device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        parse_mbus_device(v)  # raises on invalid IPv4:port
        return v

    @model_validator(mode="after")
    def validate_serial_fields(self) -> MbusConfig:
        """Ensure serial-only constraints when endpoint is serial."""
        endpoint = parse_mbus_device(self.device)
        if endpoint.type == "serial" and self.baudrate not in MBUS_BAUDRATES:
            raise ValueError(f"Baudrate must be one of {MBUS_BAUDRATES}")
        return self


class MqttConfig(BaseModel):
    """MQTT broker configuration."""

    host: str = Field(..., description="MQTT broker host (required)")
    port: int = Field(default=MQTT_DEFAULT_PORT, ge=1, le=65535, description="MQTT broker port")
    username: str | None = Field(default=None, description="MQTT username")
    password: str | None = Field(default=None, description="MQTT password")
    client_id: str | None = Field(default=None, description="MQTT client ID")
    keepalive: int = Field(default=MQTT_DEFAULT_KEEPALIVE, ge=1, description="Keepalive interval")
    qos: int = Field(default=MQTT_DEFAULT_QOS, ge=0, le=2, description="QoS level")
    base_topic: str = Field(default=MQTT_DEFAULT_BASE_TOPIC, description="Base MQTT topic")

    @model_validator(mode="after")
    def generate_client_id(self) -> MqttConfig:
        if self.client_id is None:
            self.client_id = f"libmbus2mqtt-{uuid4().hex[:8]}"
        return self


class HomeAssistantConfig(BaseModel):
    """Home Assistant integration configuration."""

    enabled: bool = Field(default=False, description="Enable HA integration")
    discovery_prefix: str = Field(
        default=HA_DEFAULT_DISCOVERY_PREFIX, description="HA discovery prefix"
    )


class PollingConfig(BaseModel):
    """Polling configuration."""

    interval: int = Field(
        default=POLLING_DEFAULT_INTERVAL, ge=1, description="Poll interval in seconds"
    )
    startup_delay: int = Field(
        default=POLLING_DEFAULT_STARTUP_DELAY, ge=0, description="Startup delay in seconds"
    )


class DeviceConfig(BaseModel):
    """Individual M-Bus device configuration."""

    id: Annotated[int, Field(ge=MBUS_ID_MIN, le=MBUS_ID_MAX, description="M-Bus device ID")]
    name: str | None = Field(default=None, description="Friendly name")
    enabled: bool = Field(default=True, description="Enable polling for this device")
    template: str | None = Field(default=None, description="HA template filename")

    @field_validator("id")
    @classmethod
    def warn_default_id(cls, v: int) -> int:
        if v == 0:
            logging.getLogger("libmbus2mqtt.config").warning(
                "Device ID 0 is the default M-Bus address - consider configuring a unique ID"
            )
        return v


class AvailabilityConfig(BaseModel):
    """Device availability configuration."""

    timeout_polls: int = Field(
        default=AVAILABILITY_DEFAULT_TIMEOUT_POLLS,
        ge=1,
        description="Consecutive failures before offline",
    )


class LogsConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    save_to_file: bool = Field(
        default=False,
        description="Enable file logging",
    )
    file: Path = Field(
        default=LOG_DEFAULT_FILE,
        description="Log file path",
    )
    max_size_mb: int = Field(
        default=LOG_DEFAULT_MAX_SIZE_MB,
        ge=1,
        le=1000,
        description="Maximum log file size in MB before rotation",
    )
    backup_count: int = Field(
        default=LOG_DEFAULT_BACKUP_COUNT,
        ge=0,
        le=100,
        description="Number of backup files to keep",
    )

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        if v.upper() not in LOG_LEVELS:
            raise ValueError(f"Log level must be one of {LOG_LEVELS}")
        return v.upper()


class AppConfig(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_prefix=f"{ENV_PREFIX}_",
        env_nested_delimiter="_",
        case_sensitive=False,
        extra="ignore",
    )

    mbus: MbusConfig
    mqtt: MqttConfig
    homeassistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    devices: list[DeviceConfig] = Field(default_factory=list)
    availability: AvailabilityConfig = Field(default_factory=AvailabilityConfig)
    logs: LogsConfig = Field(default_factory=LogsConfig)

    @classmethod
    def from_yaml(cls, path: Path | str) -> AppConfig:
        """Load configuration from YAML file with environment variable overrides."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with path.open() as f:
            yaml_config: dict[str, Any] = yaml.safe_load(f) or {}

        merged_config = _merge_env_with_config(yaml_config)
        return cls(**merged_config)

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> AppConfig:
        """Load configuration from file or default location."""
        if config_path is None:
            config_path = DEFAULT_CONFIG_FILE
        return cls.from_yaml(config_path)

    def get_device_config(self, device_id: int) -> DeviceConfig | None:
        """Get device configuration by ID."""
        for device in self.devices:
            if device.id == device_id:
                return device
        return None

    def is_device_enabled(self, device_id: int) -> bool:
        """Check if a device is enabled for polling."""
        device_config = self.get_device_config(device_id)
        if device_config is None:
            return True  # Default to enabled if not in config
        return device_config.enabled

    def save(self, path: Path | str | None = None) -> None:
        """Save configuration to YAML file."""
        if path is None:
            path = DEFAULT_CONFIG_FILE
        path = Path(path)

        # Build config dict excluding defaults where appropriate
        config_dict: dict[str, Any] = {
            "mbus": self.mbus.model_dump(exclude_none=True),
            "mqtt": self.mqtt.model_dump(exclude_none=True),
            "homeassistant": self.homeassistant.model_dump(),
            "polling": self.polling.model_dump(),
            "availability": self.availability.model_dump(),
            "logs": self.logs.model_dump(mode="json"),
        }

        if self.devices:
            config_dict["devices"] = [d.model_dump(exclude_none=True) for d in self.devices]

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            yaml.safe_dump(config_dict, f, default_flow_style=False, sort_keys=False)


def generate_example_config() -> str:
    """Generate example configuration YAML."""
    return """\
# libmbus2mqtt configuration

# M-Bus Interface (required: device)
mbus:
  device: /dev/ttyUSB0          # Serial/TTY device path OR IPv4:port (e.g. 192.168.1.50:9999)
  # baudrate: 2400              # Options: 300, 2400, 9600 (ignored for TCP)
  # timeout: 5                  # Seconds
  # retry_count: 3
  # retry_delay: 1              # Seconds
  # autoscan: true              # Scan for devices on startup

# MQTT Broker (required: host)
mqtt:
  host: localhost
  # port: 1883
  # username: null
  # password: null
  # client_id: null             # Auto-generated if not set
  # keepalive: 60
  # qos: 1
  # base_topic: libmbus2mqtt

# Home Assistant Integration
homeassistant:
  enabled: false
  # discovery_prefix: homeassistant

# Polling
polling:
  interval: 60                  # Seconds
  # startup_delay: 5            # Seconds

# Devices (optional - auto-discovered if autoscan=true)
# devices:
#   - id: 1
#     name: "Water Meter"
#     enabled: true
#     template: null            # Auto-detect

# Device Availability
availability:
  timeout_polls: 3              # Consecutive failures before offline

# Logging
logs:
  level: INFO                   # DEBUG, INFO, WARNING, ERROR, CRITICAL
  save_to_file: false           # Enable file logging
  # file: data/log/libmbus2mqtt.log  # Log file path
  # max_size_mb: 10             # Max file size before rotation (1-1000)
  # backup_count: 5             # Number of backup files to keep (0-100)
"""
