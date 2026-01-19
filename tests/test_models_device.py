"""Tests for Device and DeviceAvailability models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libmbus2mqtt.models.device import AvailabilityStatus, Device, DeviceAvailability
from libmbus2mqtt.models.mbus import MbusData


class TestAvailabilityStatus:
    """Tests for AvailabilityStatus enum."""

    def test_online_value(self) -> None:
        """Test ONLINE enum value."""
        assert AvailabilityStatus.ONLINE.value == "online"

    def test_offline_value(self) -> None:
        """Test OFFLINE enum value."""
        assert AvailabilityStatus.OFFLINE.value == "offline"

    def test_unknown_value(self) -> None:
        """Test UNKNOWN enum value."""
        assert AvailabilityStatus.UNKNOWN.value == "unknown"


class TestDeviceAvailability:
    """Tests for DeviceAvailability state machine."""

    def test_initial_state(self) -> None:
        """Test initial state is UNKNOWN."""
        avail = DeviceAvailability()
        assert avail.status == AvailabilityStatus.UNKNOWN
        assert avail.poll_fail_count == 0
        assert avail.poll_consecutive_fails == 0
        assert avail.status_changed is False

    def test_poll_success_from_unknown(self) -> None:
        """Test poll_success transitions from UNKNOWN to ONLINE."""
        avail = DeviceAvailability()
        avail.poll_success()

        assert avail.status == AvailabilityStatus.ONLINE
        assert avail.last_poll_status == "success"
        assert avail.last_poll_time is not None
        assert avail.poll_consecutive_fails == 0
        assert avail.status_changed is True

    def test_poll_success_stays_online(self) -> None:
        """Test poll_success keeps device ONLINE."""
        avail = DeviceAvailability(status=AvailabilityStatus.ONLINE)
        avail.poll_success()

        assert avail.status == AvailabilityStatus.ONLINE
        assert avail.status_changed is False  # No change

    def test_poll_success_from_offline(self) -> None:
        """Test poll_success transitions from OFFLINE to ONLINE."""
        avail = DeviceAvailability(status=AvailabilityStatus.OFFLINE)
        avail.poll_success()

        assert avail.status == AvailabilityStatus.ONLINE
        assert avail.status_changed is True

    def test_poll_fail_increments_counters(self) -> None:
        """Test poll_fail increments failure counters."""
        avail = DeviceAvailability()
        avail.poll_fail()

        assert avail.poll_fail_count == 1
        assert avail.poll_consecutive_fails == 1
        assert avail.last_poll_status == "fail"

    def test_poll_fail_threshold_triggers_offline(self) -> None:
        """Test reaching failure threshold triggers OFFLINE status."""
        avail = DeviceAvailability(timeout_threshold=3)

        # First two failures - still UNKNOWN
        avail.poll_fail()
        assert avail.status == AvailabilityStatus.UNKNOWN
        avail.poll_fail()
        assert avail.status == AvailabilityStatus.UNKNOWN

        # Third failure - goes OFFLINE
        avail.poll_fail()
        assert avail.status == AvailabilityStatus.OFFLINE
        assert avail.status_changed is True

    def test_poll_success_resets_consecutive_fails(self) -> None:
        """Test poll_success resets consecutive failure counter."""
        avail = DeviceAvailability()
        avail.poll_fail()
        avail.poll_fail()
        assert avail.poll_consecutive_fails == 2

        avail.poll_success()
        assert avail.poll_consecutive_fails == 0
        assert avail.poll_fail_count == 2  # Total not reset

    def test_reset_changed_flag(self) -> None:
        """Test reset_changed_flag method."""
        avail = DeviceAvailability()
        avail.poll_success()
        assert avail.status_changed is True

        avail.reset_changed_flag()
        assert avail.status_changed is False

    def test_custom_timeout_threshold(self) -> None:
        """Test custom timeout threshold."""
        avail = DeviceAvailability(timeout_threshold=5)

        for _ in range(4):
            avail.poll_fail()
            assert avail.status != AvailabilityStatus.OFFLINE

        avail.poll_fail()
        assert avail.status == AvailabilityStatus.OFFLINE

    def test_last_poll_time_updated(self) -> None:
        """Test last_poll_time is updated on poll."""
        from datetime import datetime

        avail = DeviceAvailability()

        before = datetime.now()
        avail.poll_success()
        after = datetime.now()

        assert avail.last_poll_time is not None
        assert before <= avail.last_poll_time <= after

    def test_poll_fail_from_online(self) -> None:
        """Test poll_fail from ONLINE state."""
        avail = DeviceAvailability(
            status=AvailabilityStatus.ONLINE,
            timeout_threshold=3,
        )

        # First fail - stays ONLINE
        avail.poll_fail()
        assert avail.status == AvailabilityStatus.ONLINE
        assert avail.status_changed is False

        # Second fail - stays ONLINE
        avail.poll_fail()
        assert avail.status == AvailabilityStatus.ONLINE

        # Third fail - goes OFFLINE
        avail.poll_fail()
        assert avail.status == AvailabilityStatus.OFFLINE
        assert avail.status_changed is True


class TestDevice:
    """Tests for Device model."""

    def test_basic_construction(self) -> None:
        """Test basic device construction."""
        device = Device(address=1)
        assert device.address == 1
        assert device.name is None
        assert device.enabled is True
        assert device.identifier is None
        assert device.mbus_data is None

    def test_named_device(self) -> None:
        """Test device with name."""
        device = Device(address=1, name="Water Meter")
        assert device.name == "Water Meter"

    def test_address_0_valid(self) -> None:
        """Test address 0 is valid."""
        device = Device(address=0)
        assert device.address == 0

    def test_address_254_valid(self) -> None:
        """Test address 254 is valid."""
        device = Device(address=254)
        assert device.address == 254

    def test_address_255_invalid(self) -> None:
        """Test address 255 is invalid."""
        with pytest.raises(ValidationError):
            Device(address=255)

    def test_address_negative_invalid(self) -> None:
        """Test negative address is invalid."""
        with pytest.raises(ValidationError):
            Device(address=-1)

    def test_display_name_with_name(self) -> None:
        """Test display_name returns custom name when set."""
        device = Device(address=1, name="My Meter")
        assert device.display_name == "My Meter"

    def test_display_name_with_model_and_serial(self) -> None:
        """Test display_name uses model and serial when no name."""
        device = Device(address=1)
        device.model = "Test Model"
        device.serial_number = "12345"
        assert device.display_name == "Test Model (12345)"

    def test_display_name_fallback_to_address(self) -> None:
        """Test display_name fallback to address."""
        device = Device(address=5)
        assert device.display_name == "M-Bus Device 5"

    def test_display_name_with_model_only(self) -> None:
        """Test display_name with model but no serial falls back to address."""
        device = Device(address=5)
        device.model = "Test Model"
        assert device.display_name == "M-Bus Device 5"

    def test_object_id_with_serial(self) -> None:
        """Test object_id returns serial_number when available."""
        device = Device(address=1)
        device.serial_number = "87654321"
        assert device.object_id == "87654321"

    def test_object_id_fallback_to_address(self) -> None:
        """Test object_id falls back to address."""
        device = Device(address=3)
        assert device.object_id == "3"

    def test_is_online_unknown(self) -> None:
        """Test is_online is False when UNKNOWN."""
        device = Device(address=1)
        assert device.is_online is False

    def test_is_online_online(self) -> None:
        """Test is_online is True when ONLINE."""
        device = Device(address=1)
        device.availability.poll_success()
        assert device.is_online is True

    def test_is_online_offline(self) -> None:
        """Test is_online is False when OFFLINE."""
        device = Device(address=1)
        device.availability.poll_fail()
        device.availability.poll_fail()
        device.availability.poll_fail()
        assert device.is_online is False

    def test_update_from_mbus_data(self, apator_mbus_data: MbusData) -> None:
        """Test update_from_mbus_data method."""
        device = Device(address=1)
        device.update_from_mbus_data(apator_mbus_data)

        assert device.mbus_data == apator_mbus_data
        assert device.identifier == "67434"
        assert device.manufacturer == "APA"
        assert device.medium == "Water"
        assert device.version == "3"
        assert device.serial_number == "67434"

    def test_update_from_mbus_data_with_product_name(
        self,
        itron_mbus_data: MbusData,
    ) -> None:
        """Test update_from_mbus_data with product name."""
        device = Device(address=1)
        device.update_from_mbus_data(itron_mbus_data)

        assert device.model == "Itron CYBLE M-Bus 1.4"

    def test_availability_default_factory(self) -> None:
        """Test availability is created with default factory."""
        device = Device(address=1)
        assert device.availability is not None
        assert device.availability.status == AvailabilityStatus.UNKNOWN

    def test_ha_discovery_published_default(self) -> None:
        """Test ha_discovery_published defaults to False."""
        device = Device(address=1)
        assert device.ha_discovery_published is False

    def test_enabled_default(self) -> None:
        """Test enabled defaults to True."""
        device = Device(address=1)
        assert device.enabled is True

    def test_enabled_can_be_false(self) -> None:
        """Test enabled can be set to False."""
        device = Device(address=1, enabled=False)
        assert device.enabled is False
