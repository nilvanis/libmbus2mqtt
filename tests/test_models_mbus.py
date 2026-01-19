"""Tests for M-Bus Pydantic models."""

from __future__ import annotations

import pytest

from libmbus2mqtt.models.mbus import DataRecord, MbusData, SlaveInformation


class TestSlaveInformation:
    """Tests for SlaveInformation model."""

    def test_field_aliases(self) -> None:
        """Test field aliases work correctly."""
        info = SlaveInformation(
            Id="12345",
            Manufacturer="ACW",
            Version="1",
            Medium="Water",
        )
        assert info.id == "12345"
        assert info.manufacturer == "ACW"
        assert info.version == "1"
        assert info.medium == "Water"

    def test_populate_by_name_with_aliases(self) -> None:
        """Test populate_by_name allows alias names."""
        info = SlaveInformation(
            Id="123",
            Manufacturer="TST",
            Version="1",
            Medium="Water",
        )
        assert info.id == "123"
        assert info.manufacturer == "TST"

    def test_populate_by_name_with_field_names(self) -> None:
        """Test populate_by_name allows field names."""
        info = SlaveInformation(
            id="123",
            manufacturer="TST",
            version="1",
            medium="Water",
        )
        assert info.id == "123"
        assert info.manufacturer == "TST"

    def test_optional_fields_default_none(self) -> None:
        """Test optional fields default to None."""
        info = SlaveInformation(
            Id="123",
            Manufacturer="TST",
            Version="1",
            Medium="Water",
        )
        assert info.product_name is None
        assert info.access_number is None
        assert info.status is None
        assert info.signature is None

    def test_all_fields_populated(self) -> None:
        """Test all fields can be populated."""
        info = SlaveInformation(
            Id="123",
            Manufacturer="TST",
            Version="1",
            ProductName="Test Device",
            Medium="Water",
            AccessNumber="42",
            Status="00",
            Signature="ABCD",
        )
        assert info.product_name == "Test Device"
        assert info.access_number == "42"
        assert info.status == "00"
        assert info.signature == "ABCD"


class TestDataRecord:
    """Tests for DataRecord model."""

    def test_minimal_record(self) -> None:
        """Test minimal data record."""
        record = DataRecord(id="0")
        assert record.id == "0"
        assert record.function is None
        assert record.value is None
        assert record.unit is None

    def test_full_record(self) -> None:
        """Test fully populated data record."""
        record = DataRecord(
            id="0",
            Function="Instantaneous value",
            StorageNumber="0",
            Tariff="1",
            Device="0",
            Unit="Volume (m m^3)",
            Value="12345",
            Timestamp="2025-01-18T12:00:00Z",
        )
        assert record.function == "Instantaneous value"
        assert record.storage_number == "0"
        assert record.tariff == "1"
        assert record.device == "0"
        assert record.unit == "Volume (m m^3)"
        assert record.value == "12345"
        assert record.timestamp == "2025-01-18T12:00:00Z"

    def test_field_aliases(self) -> None:
        """Test field aliases work correctly."""
        record = DataRecord(
            id="5",
            Function="Test",
            StorageNumber="1",
            Unit="kWh",
            Value="999",
        )
        assert record.function == "Test"
        assert record.storage_number == "1"
        assert record.unit == "kWh"
        assert record.value == "999"


class TestMbusData:
    """Tests for MbusData model."""

    @pytest.fixture
    def sample_slave_info(self) -> SlaveInformation:
        """Sample SlaveInformation for testing."""
        return SlaveInformation(
            Id="12345678",
            Manufacturer="ACW",
            Version="20",
            ProductName="Test Device",
            Medium="Water",
        )

    @pytest.fixture
    def sample_data_records(self) -> dict[str, DataRecord]:
        """Sample data records for testing."""
        return {
            "0": DataRecord(id="0", Function="Fabrication number", Value="987654"),
            "1": DataRecord(id="1", Function="Volume", Unit="m^3", Value="12345"),
        }

    def test_basic_construction(
        self,
        sample_slave_info: SlaveInformation,
        sample_data_records: dict[str, DataRecord],
    ) -> None:
        """Test basic MbusData construction."""
        data = MbusData(
            slave_information=sample_slave_info,
            data_records=sample_data_records,
        )
        assert data.slave_information == sample_slave_info
        assert len(data.data_records) == 2

    def test_device_id_property(self, sample_slave_info: SlaveInformation) -> None:
        """Test device_id property."""
        data = MbusData(slave_information=sample_slave_info)
        assert data.device_id == "12345678"

    def test_manufacturer_property(self, sample_slave_info: SlaveInformation) -> None:
        """Test manufacturer property."""
        data = MbusData(slave_information=sample_slave_info)
        assert data.manufacturer == "ACW"

    def test_product_name_property_with_value(
        self,
        sample_slave_info: SlaveInformation,
    ) -> None:
        """Test product_name property with value."""
        data = MbusData(slave_information=sample_slave_info)
        assert data.product_name == "Test Device"

    def test_product_name_fallback(self) -> None:
        """Test product_name fallback when None."""
        slave_info = SlaveInformation(
            Id="123",
            Manufacturer="TST",
            Version="1",
            Medium="Water",
        )
        data = MbusData(slave_information=slave_info)
        assert data.product_name == "M-Bus Device"

    def test_product_name_fallback_empty_string(self) -> None:
        """Test product_name fallback when empty string."""
        slave_info = SlaveInformation(
            Id="123",
            Manufacturer="TST",
            Version="1",
            ProductName="",
            Medium="Water",
        )
        data = MbusData(slave_information=slave_info)
        assert data.product_name == "M-Bus Device"

    def test_serial_number_property(
        self,
        sample_slave_info: SlaveInformation,
    ) -> None:
        """Test serial_number property."""
        data = MbusData(slave_information=sample_slave_info)
        assert data.serial_number == "12345678"

    def test_version_property(self, sample_slave_info: SlaveInformation) -> None:
        """Test version property."""
        data = MbusData(slave_information=sample_slave_info)
        assert data.version == "20"

    def test_medium_property(self, sample_slave_info: SlaveInformation) -> None:
        """Test medium property."""
        data = MbusData(slave_information=sample_slave_info)
        assert data.medium == "Water"

    def test_get_record_value_existing(
        self,
        sample_slave_info: SlaveInformation,
        sample_data_records: dict[str, DataRecord],
    ) -> None:
        """Test get_record_value for existing record."""
        data = MbusData(
            slave_information=sample_slave_info,
            data_records=sample_data_records,
        )
        assert data.get_record_value("0") == "987654"
        assert data.get_record_value("1") == "12345"

    def test_get_record_value_missing(
        self,
        sample_slave_info: SlaveInformation,
    ) -> None:
        """Test get_record_value for missing record."""
        data = MbusData(slave_information=sample_slave_info)
        assert data.get_record_value("999") is None

    def test_to_ha_state_basic(
        self,
        sample_slave_info: SlaveInformation,
        sample_data_records: dict[str, DataRecord],
    ) -> None:
        """Test to_ha_state method."""
        data = MbusData(
            slave_information=sample_slave_info,
            data_records=sample_data_records,
        )

        template = {
            "0": {"value_template": "{{ value_json.fab_number }}"},
            "1": {"value_template": "{{ value_json.volume }}"},
        }

        state = data.to_ha_state(template)
        assert state["fab_number"] == "987654"
        assert state["volume"] == "12345"

    def test_to_ha_state_skips_custom_sensors(
        self,
        sample_slave_info: SlaveInformation,
        sample_data_records: dict[str, DataRecord],
    ) -> None:
        """Test to_ha_state skips custom- prefixed sensors."""
        data = MbusData(
            slave_information=sample_slave_info,
            data_records=sample_data_records,
        )

        template = {
            "0": {"value_template": "{{ value_json.fab_number }}"},
            "custom-derived": {"value_template": "{{ value_json.derived }}"},
        }

        state = data.to_ha_state(template)
        assert "fab_number" in state
        assert "derived" not in state

    def test_to_ha_state_missing_value_template(
        self,
        sample_slave_info: SlaveInformation,
    ) -> None:
        """Test to_ha_state handles missing value_template."""
        data = MbusData(slave_information=sample_slave_info)

        template: dict[str, dict[str, str]] = {
            "0": {"name": "Test"},  # No value_template
        }

        state = data.to_ha_state(template)
        assert state == {}

    def test_to_ha_state_missing_record(
        self,
        sample_slave_info: SlaveInformation,
    ) -> None:
        """Test to_ha_state handles missing record gracefully."""
        data = MbusData(slave_information=sample_slave_info, data_records={})

        template = {
            "999": {"value_template": "{{ value_json.missing }}"},
        }

        state = data.to_ha_state(template)
        # Value will be None since record doesn't exist
        assert state["missing"] is None
