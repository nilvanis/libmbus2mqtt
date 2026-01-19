"""M-Bus data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SlaveInformation(BaseModel):
    """M-Bus slave device information from XML response."""

    id: str = Field(alias="Id")
    manufacturer: str = Field(alias="Manufacturer")
    version: str = Field(alias="Version")
    product_name: str | None = Field(default=None, alias="ProductName")
    medium: str = Field(alias="Medium")
    access_number: str | None = Field(default=None, alias="AccessNumber")
    status: str | None = Field(default=None, alias="Status")
    signature: str | None = Field(default=None, alias="Signature")

    model_config = {"populate_by_name": True}


class DataRecord(BaseModel):
    """M-Bus data record from XML response."""

    id: str
    function: str | None = Field(default=None, alias="Function")
    storage_number: str | None = Field(default=None, alias="StorageNumber")
    tariff: str | None = Field(default=None, alias="Tariff")
    device: str | None = Field(default=None, alias="Device")
    unit: str | None = Field(default=None, alias="Unit")
    value: str | None = Field(default=None, alias="Value")
    timestamp: str | None = Field(default=None, alias="Timestamp")

    model_config = {"populate_by_name": True}


class MbusData(BaseModel):
    """Complete M-Bus device data from XML response."""

    slave_information: SlaveInformation
    data_records: dict[str, DataRecord] = Field(default_factory=dict)

    @property
    def device_id(self) -> str:
        """Get device ID from slave information."""
        return self.slave_information.id

    @property
    def manufacturer(self) -> str:
        """Get manufacturer from slave information."""
        return self.slave_information.manufacturer

    @property
    def product_name(self) -> str:
        """Get product name, with fallback."""
        return self.slave_information.product_name or "M-Bus Device"

    @property
    def serial_number(self) -> str:
        """Get serial number (same as ID)."""
        return self.slave_information.id

    @property
    def version(self) -> str:
        """Get firmware version."""
        return self.slave_information.version

    @property
    def medium(self) -> str:
        """Get medium type."""
        return self.slave_information.medium

    def get_record_value(self, record_id: str) -> str | None:
        """Get value from a data record by ID."""
        record = self.data_records.get(record_id)
        return record.value if record else None

    def to_ha_state(self, template: dict[str, dict[str, str]]) -> dict[str, str | None]:
        """
        Convert data records to Home Assistant state payload.

        Args:
            template: HA template with component_id -> config mapping

        Returns:
            Dictionary with json field names and values
        """
        import re

        state: dict[str, str | None] = {}
        regex = re.compile(r"(?<=value_json\.)(\S+)")

        for component_id, config in template.items():
            # Skip custom sensors (they derive values from other fields)
            if component_id.startswith("custom-"):
                continue

            value_template = config.get("value_template", "")
            match = regex.search(value_template)
            if match:
                json_name = match.group()
                state[json_name] = self.get_record_value(component_id)

        return state
