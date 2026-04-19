"""Tests for Home Assistant device templates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from libmbus2mqtt import templates
from libmbus2mqtt.templates import (
    clear_cache,
    count_template_records,
    find_template,
    get_template_for_device,
    load_template,
    resolve_template,
)


@pytest.fixture(autouse=True)
def clear_template_cache() -> None:
    """Clear template cache before each test."""
    clear_cache()


class TestFindTemplate:
    """Tests for bundled template matching."""

    def test_find_apator_template(self) -> None:
        filename = find_template("APA", None, 12)
        assert filename == "apt-mbus-na-1.json"

    def test_find_apator_template_with_empty_product(self) -> None:
        filename = find_template("APA", "", 12)
        assert filename == "apt-mbus-na-1.json"

    def test_find_itron_dr8_template(self) -> None:
        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4", 8)
        assert filename == "itron_cyble_1_4-dr8.json"

    def test_find_itron_dr7_template(self) -> None:
        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4", 7)
        assert filename == "itron_cyble_1_4-dr7.json"

    def test_find_kamstrup_template(self) -> None:
        filename = find_template("KAM", "Kamstrup 382 (6850-005)", 12)
        assert filename == "kamstrup_multical_401.json"

    def test_find_zri_template(self) -> None:
        filename = find_template("ZRI", None, 18)
        assert filename == "zri.json"

    def test_unknown_manufacturer_returns_none(self) -> None:
        assert find_template("UNKNOWN", None, 1) is None

    def test_wrong_product_name_returns_none(self) -> None:
        assert find_template("ACW", "Wrong Product", 8) is None

    def test_counted_entries_fallback_when_count_missing(self) -> None:
        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4")
        assert filename == "itron_cyble_1_4-dr8.json"


class TestTemplateResolution:
    """Tests for template resolution behavior."""

    def test_explicit_template_override_wins(self) -> None:
        selection = resolve_template(
            manufacturer="ACW",
            product_name="Itron CYBLE M-Bus 1.4",
            data_record_count=7,
            explicit_filename="itron_cyble_1_4-dr8.json",
        )
        assert selection.mode == "explicit"
        assert selection.source == "explicit"
        assert selection.filename == "itron_cyble_1_4-dr8.json"
        assert selection.template is not None
        assert "7" in selection.template

    def test_generic_when_no_match(self) -> None:
        selection = resolve_template(
            manufacturer="UNKNOWN",
            product_name="Unknown",
            data_record_count=5,
        )
        assert selection.mode == "generic"
        assert selection.source == "generic"
        assert selection.template is None


class TestLoadTemplate:
    """Tests for loading templates."""

    def test_load_bundled_template(self) -> None:
        template = load_template("itron_cyble_1_4-dr8.json")
        assert template is not None
        assert "7" in template

    def test_load_nonexistent_template(self) -> None:
        assert load_template("nonexistent.json") is None

    def test_template_caching(self) -> None:
        template1 = load_template("itron_cyble_1_4-dr8.json")
        template2 = load_template("itron_cyble_1_4-dr8.json")
        assert template1 is template2

    def test_cache_clear(self) -> None:
        template1 = load_template("itron_cyble_1_4-dr8.json")
        clear_cache()
        template2 = load_template("itron_cyble_1_4-dr8.json")
        assert template1 == template2
        assert template1 is not template2


class TestTemplateContent:
    """Tests for template content and counts."""

    def test_itron_dr8_template_structure(self) -> None:
        template = load_template("itron_cyble_1_4-dr8.json")
        assert template is not None
        assert "0" in template
        assert "name" in template["0"]
        assert "value_template" in template["0"]

    def test_itron_dr7_template_has_no_month_start(self) -> None:
        template = load_template("itron_cyble_1_4-dr7.json")
        assert template is not None
        assert "6" in template
        assert "manufacturer_specific" in template["6"]["value_template"]

    def test_count_template_records_ignores_custom_entries(self) -> None:
        template = {
            "0": {"value_template": "{{ value_json.a }}"},
            "1": {"value_template": "{{ value_json.b }}"},
            "custom-daily": {"value_template": "{{ value_json.c }}"},
        }
        assert count_template_records(template) == 2

    def test_all_templates_have_required_fields(self) -> None:
        template_files = [
            "apt-mbus-na-1.json",
            "itron_cyble_1_4-dr7.json",
            "itron_cyble_1_4-dr8.json",
            "kamstrup_multical_401.json",
            "zri.json",
        ]

        for filename in template_files:
            template = load_template(filename)
            assert template is not None, f"Failed to load {filename}"

            for sensor_id, sensor_config in template.items():
                assert "name" in sensor_config, f"{filename}[{sensor_id}] missing 'name'"
                assert "value_template" in sensor_config, (
                    f"{filename}[{sensor_id}] missing 'value_template'"
                )


class TestGetTemplateForDevice:
    """Tests for get_template_for_device helper."""

    def test_get_template_for_itron_dr8(self) -> None:
        template = get_template_for_device("ACW", "Itron CYBLE M-Bus 1.4", 8)
        assert template is not None
        assert "7" in template

    def test_get_template_for_itron_dr7(self) -> None:
        template = get_template_for_device("ACW", "Itron CYBLE M-Bus 1.4", 7)
        assert template is not None
        assert "7" not in template

    def test_get_template_for_unknown_device(self) -> None:
        assert get_template_for_device("UNKNOWN", None, 1) is None


class TestUserTemplates:
    """Tests for user-defined templates."""

    @pytest.fixture
    def user_templates_dir(self, tmp_path: Path) -> Path:
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        return templates_dir

    def test_user_template_takes_priority(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user_template = {
            "0": {
                "name": "User Defined Sensor",
                "value_template": "{{ value_json.user_sensor }}",
            }
        }
        (user_templates_dir / "itron_cyble_1_4-dr8.json").write_text(json.dumps(user_template))

        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        template = load_template("itron_cyble_1_4-dr8.json")
        assert template is not None
        assert template["0"]["name"] == "User Defined Sensor"

    def test_user_index_takes_priority_with_count(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user_index = {
            "custom_device.json": {
                "Manufacturer": "ACW",
                "ProductName": "Itron CYBLE M-Bus 1.4",
                "DataRecordCount": 8,
            }
        }
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))
        (user_templates_dir / "custom_device.json").write_text(
            json.dumps({"0": {"name": "Custom", "value_template": "{{ value_json.x }}"}})
        )

        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4", 8)
        assert filename == "custom_device.json"

    def test_user_index_without_count_falls_back_for_any_count(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user_index = {
            "custom_device.json": {
                "Manufacturer": "XYZ",
                "ProductName": "OnlyOne",
            }
        }
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))
        (user_templates_dir / "custom_device.json").write_text(
            json.dumps({"0": {"name": "Only One", "value_template": "{{ value_json.a }}"}})
        )

        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        assert find_template("XYZ", "OnlyOne", 4) == "custom_device.json"
        assert find_template("KAM", "Kamstrup 382 (6850-005)", 12) == "kamstrup_multical_401.json"

    def test_user_index_invalid_count_ignored(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user_index: dict[str, dict[str, Any]] = {
            "custom_device.json": {
                "Manufacturer": "ACW",
                "ProductName": "Itron CYBLE M-Bus 1.4",
                "DataRecordCount": "eight",
            }
        }
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        assert find_template("ACW", "Itron CYBLE M-Bus 1.4", 8) == "itron_cyble_1_4-dr8.json"

    def test_resolve_template_ignores_candidate_with_wrong_numeric_record_count(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user_index = {
            "custom_device.json": {
                "Manufacturer": "ACW",
                "ProductName": "Itron CYBLE M-Bus 1.4",
                "DataRecordCount": 8,
            }
        }
        wrong_template = {
            str(index): {
                "name": f"Record {index}",
                "value_template": f"{{{{ value_json.record_{index} }}}}",
            }
            for index in range(7)
        }
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))
        (user_templates_dir / "custom_device.json").write_text(json.dumps(wrong_template))

        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        selection = resolve_template(
            manufacturer="ACW",
            product_name="Itron CYBLE M-Bus 1.4",
            data_record_count=8,
        )
        assert selection.filename == "itron_cyble_1_4-dr8.json"
        assert selection.source == "bundled_index"


class TestFixtureTemplateMatching:
    """Tests that parsed fixtures match expected templates."""

    def test_apator_fixture_template_match(self, apator_mbus_data: Any) -> None:
        filename = find_template(
            apator_mbus_data.manufacturer,
            apator_mbus_data.raw_product_name,
            apator_mbus_data.datarecord_count,
        )
        assert filename == "apt-mbus-na-1.json"

    def test_itron_dr8_fixture_template_match(self, itron_mbus_data: Any) -> None:
        filename = find_template(
            itron_mbus_data.manufacturer,
            itron_mbus_data.raw_product_name,
            itron_mbus_data.datarecord_count,
        )
        assert filename == "itron_cyble_1_4-dr8.json"

    def test_itron_dr7_fixture_template_match(self, itron_dr7_mbus_data: Any) -> None:
        filename = find_template(
            itron_dr7_mbus_data.manufacturer,
            itron_dr7_mbus_data.raw_product_name,
            itron_dr7_mbus_data.datarecord_count,
        )
        assert filename == "itron_cyble_1_4-dr7.json"

    def test_kamstrup_fixture_template_match(self, kamstrup_mbus_data: Any) -> None:
        filename = find_template(
            kamstrup_mbus_data.manufacturer,
            kamstrup_mbus_data.raw_product_name,
            kamstrup_mbus_data.datarecord_count,
        )
        assert filename == "kamstrup_multical_401.json"

    def test_bmeters_fixture_template_match(self, bmeters_mbus_data: Any) -> None:
        filename = find_template(
            bmeters_mbus_data.manufacturer,
            bmeters_mbus_data.raw_product_name,
            bmeters_mbus_data.datarecord_count,
        )
        assert filename == "zri.json"
