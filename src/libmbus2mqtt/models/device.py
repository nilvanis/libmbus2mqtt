"""Device models and availability tracking."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from libmbus2mqtt.models.mbus import MbusData


class AvailabilityStatus(str, Enum):
    """Device availability status."""

    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class DeviceAvailability(BaseModel):
    """Track device availability based on poll success/failure."""

    status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    last_poll_status: str | None = None
    last_poll_time: datetime | None = None
    poll_fail_count: int = 0
    poll_consecutive_fails: int = 0
    timeout_threshold: int = 3
    status_changed: bool = False

    def poll_success(self) -> None:
        """Record a successful poll."""
        old_status = self.status
        self.status = AvailabilityStatus.ONLINE
        self.last_poll_status = "success"
        self.last_poll_time = datetime.now()
        self.poll_consecutive_fails = 0
        self.status_changed = old_status != self.status

    def poll_fail(self) -> None:
        """Record a failed poll."""
        old_status = self.status
        self.last_poll_status = "fail"
        self.last_poll_time = datetime.now()
        self.poll_fail_count += 1
        self.poll_consecutive_fails += 1

        if self.poll_consecutive_fails >= self.timeout_threshold:
            self.status = AvailabilityStatus.OFFLINE

        self.status_changed = old_status != self.status

    def reset_changed_flag(self) -> None:
        """Reset the status_changed flag after publishing."""
        self.status_changed = False


class Device(BaseModel):
    """M-Bus device representation."""

    # Device identification
    address: int = Field(ge=0, le=254, description="M-Bus primary address")
    name: str | None = Field(default=None, description="Friendly name from config")
    enabled: bool = Field(default=True, description="Whether to poll this device")
    template_name: str | None = Field(default=None, description="HA template filename")

    # Data from M-Bus (populated after successful poll)
    identifier: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    medium: str | None = None
    version: str | None = None
    serial_number: str | None = None

    # Runtime state
    mbus_data: MbusData | None = Field(default=None, exclude=True)
    availability: DeviceAvailability = Field(default_factory=DeviceAvailability)

    # Home Assistant state
    ha_template: dict[str, dict[str, str]] | None = Field(default=None, exclude=True)
    ha_discovery_published: bool = Field(default=False, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    def update_from_mbus_data(self, data: MbusData) -> None:
        """Update device info from parsed M-Bus data."""
        self.mbus_data = data
        self.identifier = data.device_id
        self.manufacturer = data.manufacturer
        self.model = data.product_name
        self.medium = data.medium
        self.version = data.version
        self.serial_number = data.serial_number

    @property
    def display_name(self) -> str:
        """Get display name for the device."""
        if self.name:
            return self.name
        if self.model and self.serial_number:
            return f"{self.model} ({self.serial_number})"
        return f"M-Bus Device {self.address}"

    @property
    def object_id(self) -> str:
        """Get unique object ID for MQTT topics."""
        if self.serial_number:
            return self.serial_number
        return str(self.address)

    @property
    def is_online(self) -> bool:
        """Check if device is online."""
        return self.availability.status == AvailabilityStatus.ONLINE
