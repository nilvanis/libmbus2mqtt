"""Tests for M-Bus XML parser."""

from __future__ import annotations

import pytest

from libmbus2mqtt.mbus.parser import MbusParseError, parse_xml, xml_to_dict


class TestParseXml:
    """Tests for parse_xml function."""

    def test_parse_apator_fixture(self, apator_xml: str) -> None:
        """Test parsing Apator fixture."""
        data = parse_xml(apator_xml)

        assert data.device_id == "67434"
        assert data.manufacturer == "APA"
        assert data.version == "3"
        assert data.medium == "Water"
        # Empty ProductName should return fallback
        assert data.product_name == "M-Bus Device"

    def test_parse_itron_fixture(self, itron_xml: str) -> None:
        """Test parsing Itron Cyble fixture."""
        data = parse_xml(itron_xml)

        assert data.device_id == "22003204"
        assert data.manufacturer == "ACW"
        assert data.version == "20"
        assert data.product_name == "Itron CYBLE M-Bus 1.4"
        assert data.medium == "Water"

    def test_parse_kamstrup_fixture(self, kamstrup_xml: str) -> None:
        """Test parsing Kamstrup Multical 401 fixture."""
        data = parse_xml(kamstrup_xml)

        assert data.device_id == "2"
        assert data.manufacturer == "KAM"
        assert data.version == "1"
        assert data.product_name == "Kamstrup 382 (6850-005)"
        assert data.medium == "Heat: Outlet"

    def test_parse_bmeters_fixture(self, bmeters_xml: str) -> None:
        """Test parsing B Meters FRM-MB1 (ZRI) fixture."""
        data = parse_xml(bmeters_xml)

        assert data.device_id == "12841572"
        assert data.manufacturer == "ZRI"
        assert data.version == "0"
        assert data.medium == "Cold water"

    def test_parse_zenner_fixture(self, zenner_xml: str) -> None:
        """Test parsing Zenner EDC (ZRI) fixture."""
        data = parse_xml(zenner_xml)

        assert data.device_id == "12995211"
        assert data.manufacturer == "ZRI"
        assert data.version == "0"
        assert data.medium == "Cold water"

    def test_all_fixtures_parse_successfully(
        self,
        all_xml_fixtures: tuple[str, str],
    ) -> None:
        """Test all fixtures parse without errors."""
        name, xml_content = all_xml_fixtures
        data = parse_xml(xml_content)
        assert data.slave_information is not None
        assert data.manufacturer is not None

    def test_data_records_parsed(self, apator_xml: str) -> None:
        """Test data records are parsed correctly."""
        data = parse_xml(apator_xml)

        assert len(data.data_records) > 0
        assert "0" in data.data_records
        assert "2" in data.data_records

        # Check specific record
        record_0 = data.data_records["0"]
        assert record_0.function == "Instantaneous value"
        assert record_0.unit == "Fabrication number"
        assert record_0.value == "345678"

    def test_data_record_fields(self, kamstrup_xml: str) -> None:
        """Test data record fields are parsed."""
        data = parse_xml(kamstrup_xml)

        # Energy record
        record_0 = data.data_records["0"]
        assert record_0.function == "Instantaneous value"
        assert record_0.storage_number == "0"
        assert record_0.unit == "Energy (kWh)"
        assert record_0.value == "87247"

    def test_get_record_value_existing(self, apator_xml: str) -> None:
        """Test get_record_value for existing records."""
        data = parse_xml(apator_xml)

        assert data.get_record_value("0") == "345678"
        assert data.get_record_value("2") == "33803"

    def test_get_record_value_nonexistent(self, apator_xml: str) -> None:
        """Test get_record_value for non-existing record."""
        data = parse_xml(apator_xml)
        assert data.get_record_value("999") is None

    def test_invalid_xml_raises_error(self) -> None:
        """Test invalid XML raises MbusParseError."""
        with pytest.raises(MbusParseError, match="Invalid XML"):
            parse_xml("not valid xml")

    def test_unclosed_tag_raises_error(self) -> None:
        """Test unclosed XML tag raises MbusParseError."""
        with pytest.raises(MbusParseError, match="Invalid XML"):
            parse_xml("<MBusData><SlaveInformation>")

    def test_missing_slave_information_raises_error(self) -> None:
        """Test missing SlaveInformation raises MbusParseError."""
        xml = "<MBusData><DataRecord id='0'><Value>123</Value></DataRecord></MBusData>"
        with pytest.raises(MbusParseError, match="Missing SlaveInformation"):
            parse_xml(xml)

    def test_empty_xml_raises_error(self) -> None:
        """Test empty XML raises MbusParseError."""
        with pytest.raises(MbusParseError):
            parse_xml("")

    def test_missing_required_slave_fields(self) -> None:
        """Test missing required slave fields raises MbusParseError."""
        xml = """<MBusData>
            <SlaveInformation>
                <Id>123</Id>
            </SlaveInformation>
        </MBusData>"""
        with pytest.raises(MbusParseError, match="Invalid SlaveInformation"):
            parse_xml(xml)

    def test_data_record_without_id_skipped(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test DataRecord without id attribute is skipped with warning."""
        xml = """<MBusData>
            <SlaveInformation>
                <Id>123</Id>
                <Manufacturer>TST</Manufacturer>
                <Version>1</Version>
                <Medium>Water</Medium>
            </SlaveInformation>
            <DataRecord><Value>100</Value></DataRecord>
            <DataRecord id="0"><Value>200</Value></DataRecord>
        </MBusData>"""

        data = parse_xml(xml)
        assert len(data.data_records) == 1  # Only the one with id
        assert "0" in data.data_records
        assert "DataRecord missing 'id' attribute" in caplog.text


class TestXmlToDict:
    """Tests for xml_to_dict function."""

    def test_basic_conversion(self, apator_xml: str) -> None:
        """Test basic XML to dict conversion."""
        result = xml_to_dict(apator_xml)

        assert "SlaveInformation" in result
        assert "DataRecord" in result

    def test_slave_information_structure(self, itron_xml: str) -> None:
        """Test SlaveInformation is properly converted."""
        result = xml_to_dict(itron_xml)
        slave_info = result["SlaveInformation"]

        assert isinstance(slave_info, dict)
        assert slave_info["Id"] == "22003204"
        assert slave_info["Manufacturer"] == "ACW"
        assert slave_info["ProductName"] == "Itron CYBLE M-Bus 1.4"

    def test_data_records_structure(self, kamstrup_xml: str) -> None:
        """Test DataRecords are properly converted."""
        result = xml_to_dict(kamstrup_xml)
        data_records = result["DataRecord"]

        assert isinstance(data_records, dict)
        assert "0" in data_records
        assert data_records["0"]["Unit"] == "Energy (kWh)"
        assert data_records["0"]["Value"] == "87247"

    def test_invalid_xml_raises_error(self) -> None:
        """Test invalid XML raises MbusParseError."""
        with pytest.raises(MbusParseError, match="Invalid XML"):
            xml_to_dict("not valid xml")
