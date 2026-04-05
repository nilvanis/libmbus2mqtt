"""Tests for persistent runtime state and daemon identity sync."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, call

import pytest

from libmbus2mqtt.main import Daemon
from libmbus2mqtt.models.device import Device
from libmbus2mqtt.models.mbus import DataRecord, MbusData, SlaveInformation
from libmbus2mqtt.state import StateStore


def make_mbus_data(
    *,
    object_id: str,
    manufacturer: str = "ACW",
    product_name: str | None = "Itron CYBLE M-Bus 1.4",
    record_count: int = 8,
) -> MbusData:
    """Build synthetic M-Bus payloads for identity and rematch tests."""
    return MbusData(
        slave_information=SlaveInformation(
            Id=object_id,
            Manufacturer=manufacturer,
            Version="20",
            ProductName=product_name,
            Medium="Water",
        ),
        data_records={
            str(index): DataRecord(id=str(index), Function="Instantaneous value", Value=str(index))
            for index in range(record_count)
        },
    )


@pytest.fixture
def state_store(tmp_path_factory: pytest.TempPathFactory) -> StateStore:
    """Create a temporary SQLite state store."""
    return StateStore(tmp_path_factory.mktemp("state") / "libmbus2mqtt.db")


@pytest.fixture
def daemon(minimal_app_config, state_store: StateStore) -> Daemon:
    """Create daemon with mocked runtime dependencies."""
    daemon = Daemon(minimal_app_config)
    daemon._state_store = state_store
    daemon._mqtt = MagicMock()
    daemon._ha_discovery = MagicMock()
    return daemon


def count_identities(state_store: StateStore) -> int:
    """Return number of persisted device identities."""
    with sqlite3.connect(state_store.db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM device_identity").fetchone()
    return 0 if row is None else int(row[0])


class TestDaemonIdentitySync:
    """Tests for daemon identity tracking and replacement logic."""

    def test_first_start_bootstraps_without_replaced_device(
        self,
        daemon: Daemon,
        state_store: StateStore,
    ) -> None:
        device = Device(address=1, name="Water Meter")
        device.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))

        result = daemon._sync_device_runtime_state(device, first_data=True)
        daemon._persist_address_binding(device)

        assert result.should_publish_discovery is True
        assert count_identities(state_store) == 1

        identity = state_store.get_identity(device.identity_key or "")
        binding = state_store.get_address_binding(1)
        assert identity is not None
        assert binding is not None
        assert identity.status == "active"
        assert binding.identity_key == identity.identity_key
        assert state_store.list_events()[0]["event_type"] == "bootstrap"

    def test_display_name_change_updates_current_device_only(
        self,
        daemon: Daemon,
        state_store: StateStore,
    ) -> None:
        device = Device(address=1, name="Water Meter")
        payload = make_mbus_data(object_id="A1", record_count=7)
        device.update_from_mbus_data(payload)

        daemon._sync_device_runtime_state(device, first_data=True)
        daemon._persist_address_binding(device)

        device.name = "Kitchen Meter"
        device.update_from_mbus_data(payload)

        result = daemon._sync_device_runtime_state(device, first_data=False)
        daemon._persist_address_binding(device)

        assert result.renamed is True
        assert result.identity_changed is False
        assert count_identities(state_store) == 1

        binding = state_store.get_address_binding(1)
        assert binding is not None
        assert binding.published_device_name == "Kitchen Meter"
        assert state_store.list_events()[-1]["event_type"] == "rename"

    def test_same_identity_record_count_change_rematches_template(
        self,
        daemon: Daemon,
        state_store: StateStore,
    ) -> None:
        device = Device(address=1)
        device.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))

        daemon._sync_device_runtime_state(device, first_data=True)
        daemon._persist_address_binding(device)

        device.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=8))

        result = daemon._sync_device_runtime_state(device, first_data=False)
        daemon._persist_address_binding(device)

        assert result.template_rematched is True
        assert result.identity_changed is False

        binding = state_store.get_address_binding(1)
        assert binding is not None
        assert binding.datarecord_count == 8
        assert state_store.list_events()[-1]["event_type"] == "template_rematch"

    def test_explicit_template_disables_auto_rematch(
        self,
        daemon: Daemon,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        device = Device(address=1, template_name="itron_cyble_1_4-dr7.json")
        device.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))

        daemon._sync_device_runtime_state(device, first_data=True)
        daemon._persist_address_binding(device)

        device.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=8))

        result = daemon._sync_device_runtime_state(device, first_data=False)

        assert result.template_rematched is False
        assert "explicit template" in caplog.text

    def test_back_and_forth_replacement_reuses_identity_rows(
        self,
        daemon: Daemon,
        state_store: StateStore,
    ) -> None:
        device = Device(address=1, name="Water Meter")

        device.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))
        daemon._sync_device_runtime_state(device, first_data=True)
        daemon._persist_address_binding(device)

        device.update_from_mbus_data(make_mbus_data(object_id="B1", record_count=7))
        result_b1 = daemon._sync_device_runtime_state(device, first_data=False)
        daemon._persist_address_binding(device)

        device.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))
        result_a2 = daemon._sync_device_runtime_state(device, first_data=False)
        daemon._persist_address_binding(device)

        device.update_from_mbus_data(make_mbus_data(object_id="B1", record_count=7))
        result_b2 = daemon._sync_device_runtime_state(device, first_data=False)
        daemon._persist_address_binding(device)

        assert result_b1.identity_changed is True
        assert result_a2.identity_changed is True
        assert result_b2.identity_changed is True
        assert count_identities(state_store) == 2

        identity_a = state_store.get_identity_by_tuple("A1", "ACW", "Itron CYBLE M-Bus 1.4")
        identity_b = state_store.get_identity_by_tuple("B1", "ACW", "Itron CYBLE M-Bus 1.4")
        assert identity_a is not None
        assert identity_b is not None
        assert identity_a.activation_count == 2
        assert identity_b.activation_count == 2
        assert identity_a.status == "replaced"
        assert identity_b.status == "active"

        assert daemon._ha_discovery.publish_replaced_device.call_count == 3
        assert daemon._mqtt.publish_device_availability.call_count == 3

    def test_replacement_publishes_new_device_online_immediately(
        self,
        daemon: Daemon,
    ) -> None:
        device = Device(address=1, name="Water Meter")
        daemon._devices[1] = device
        daemon._mbus = MagicMock()

        device.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))
        daemon._sync_device_runtime_state(device, first_data=True)
        daemon._persist_address_binding(device)
        device.availability.poll_success()
        device.availability.reset_changed_flag()

        daemon._mqtt.reset_mock()
        daemon._mbus.poll.return_value = make_mbus_data(object_id="B1", record_count=7)

        daemon._poll_devices()

        assert call("A1", "offline") in daemon._mqtt.publish_device_availability.call_args_list
        assert call("B1", "online") in daemon._mqtt.publish_device_availability.call_args_list

    def test_same_identity_move_rebinds_to_new_address_without_duplicate_binding(
        self,
        daemon: Daemon,
        state_store: StateStore,
    ) -> None:
        device_one = Device(address=1)
        device_one.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))
        daemon._sync_device_runtime_state(device_one, first_data=True)
        daemon._persist_address_binding(device_one)

        device_two = Device(address=2)
        device_two.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))
        daemon._sync_device_runtime_state(device_two, first_data=True)
        daemon._persist_address_binding(device_two)

        binding_one = state_store.get_address_binding(1)
        binding_two = state_store.get_address_binding(2)
        assert binding_one is None
        assert binding_two is not None
        assert binding_two.identity_key == device_two.identity_key
        assert count_identities(state_store) == 1

    def test_mqtt_reconnect_republishes_device_availability_for_current_binding_only(
        self,
        daemon: Daemon,
    ) -> None:
        device_one = Device(address=1)
        device_one.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))
        daemon._sync_device_runtime_state(device_one, first_data=True)
        daemon._persist_address_binding(device_one)
        device_one.availability.poll_success()
        device_one.availability.reset_changed_flag()

        device_two = Device(address=2)
        device_two.update_from_mbus_data(make_mbus_data(object_id="A1", record_count=7))
        daemon._sync_device_runtime_state(device_two, first_data=True)
        daemon._persist_address_binding(device_two)
        device_two.availability.poll_success()
        device_two.availability.reset_changed_flag()

        daemon._devices[1] = device_one
        daemon._devices[2] = device_two
        daemon._mqtt.reset_mock()
        daemon._ha_discovery.reset_mock()

        daemon._on_mqtt_connect()

        daemon._ha_discovery.publish_device_discovery.assert_called_once_with(device_two)
        daemon._mqtt.publish_device_availability.assert_called_once_with("A1", "online")

    def test_scan_publishes_bridge_info_immediately(
        self,
        daemon: Daemon,
    ) -> None:
        daemon._mbus = MagicMock()
        daemon._mbus.scan.return_value = [3, 7]
        daemon._bridge_info = MagicMock()

        daemon._scan_devices()

        assert sorted(daemon._devices) == [3, 7]
        daemon._bridge_info.set_discovered_devices.assert_called_once_with(2)
        daemon._bridge_info.set_last_scan.assert_called_once_with()
        daemon._bridge_info.publish.assert_called_once_with()
