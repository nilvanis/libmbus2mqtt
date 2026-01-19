"""M-Bus XML response parser."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from libmbus2mqtt.logging import get_logger
from libmbus2mqtt.models.mbus import DataRecord, MbusData, SlaveInformation

logger = get_logger("mbus.parser")


class MbusParseError(Exception):
    """Error parsing M-Bus XML response."""

    pass


def parse_xml(xml_string: str) -> MbusData:
    """
    Parse M-Bus XML response into Pydantic models.

    Args:
        xml_string: Raw XML string from libmbus

    Returns:
        MbusData object with parsed data

    Raises:
        MbusParseError: If XML parsing fails
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        raise MbusParseError(f"Invalid XML: {e}") from e

    # Parse SlaveInformation
    slave_info_elem = root.find("SlaveInformation")
    if slave_info_elem is None:
        raise MbusParseError("Missing SlaveInformation element")

    slave_info_dict = _element_to_dict(slave_info_elem)
    try:
        slave_info = SlaveInformation(**slave_info_dict)
    except Exception as e:
        raise MbusParseError(f"Invalid SlaveInformation: {e}") from e

    # Parse DataRecords
    data_records: dict[str, DataRecord] = {}
    for record_elem in root.findall("DataRecord"):
        record_id = record_elem.get("id")
        if record_id is None:
            logger.warning("DataRecord missing 'id' attribute, skipping")
            continue

        record_dict = _element_to_dict(record_elem)
        record_dict["id"] = record_id

        try:
            data_records[record_id] = DataRecord(**record_dict)
        except Exception as e:
            logger.warning(f"Failed to parse DataRecord {record_id}: {e}")
            continue

    return MbusData(slave_information=slave_info, data_records=data_records)


def _element_to_dict(element: ET.Element) -> dict[str, str | None]:
    """Convert XML element children to dictionary."""
    result: dict[str, str | None] = {}
    for child in element:
        # Skip nested complex elements (like DataRecord within SlaveInformation)
        if len(child) > 0:
            continue
        result[child.tag] = child.text
    return result


def xml_to_dict(xml_string: str) -> dict[str, object]:
    """
    Parse M-Bus XML to raw dictionary (for compatibility with v1 templates).

    This provides the same structure as v1's xml2dict method.

    Args:
        xml_string: Raw XML string from libmbus

    Returns:
        Dictionary with SlaveInformation and DataRecord sections
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        raise MbusParseError(f"Invalid XML: {e}") from e

    def get_children(element: ET.Element) -> dict[str, object]:
        result: dict[str, object] = {}
        for child in element:
            if child.tag == "DataRecord":
                if "DataRecord" not in result:
                    result["DataRecord"] = {}
                record_id = child.get("id", "unknown")
                data_records = result["DataRecord"]
                if isinstance(data_records, dict):
                    data_records[record_id] = get_children(child)
            elif child.tag == "SlaveInformation":
                result[child.tag] = get_children(child)
            else:
                result[child.tag] = child.text
        return result

    return get_children(root)
