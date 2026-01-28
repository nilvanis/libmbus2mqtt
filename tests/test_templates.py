"""Tests for Home Assistant device templates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from libmbus2mqtt import templates
from libmbus2mqtt.templates import (
    clear_cache,
    find_template,
    get_template_for_device,
    load_template,
)


@pytest.fixture(autouse=True)
def clear_template_cache() -> None:
    """Clear template cache before each test."""
    clear_cache()


# ============================================================================
# Template Matching Tests
# ============================================================================


class TestFindTemplate:
    """Tests for find_template function."""

    def test_find_apator_template(self) -> None:
        """Test finding Apator template by manufacturer only."""
        filename = find_template("APA", None)
        assert filename == "apt-mbus-na-1.json"

    def test_find_apator_template_with_empty_product(self) -> None:
        """Test finding Apator template with empty product name."""
        filename = find_template("APA", "")
        # Empty string should also match null ProductName
        assert filename == "apt-mbus-na-1.json"

    def test_find_itron_template(self) -> None:
        """Test finding Itron template by manufacturer and product."""
        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4")
        assert filename == "itron_cyble_1_4.json"

    def test_find_kamstrup_template(self) -> None:
        """Test finding Kamstrup template."""
        filename = find_template("KAM", "Kamstrup 382 (6850-005)")
        assert filename == "kamstrup_multical_401.json"

    def test_find_zri_template(self) -> None:
        """Test finding ZRI template."""
        filename = find_template("ZRI", None)
        assert filename == "zri.json"

    def test_find_zri_with_any_product(self) -> None:
        """Test ZRI matches any product name since ProductName is null."""
        filename = find_template("ZRI", "Some Product")
        assert filename == "zri.json"

    def test_unknown_manufacturer_returns_none(self) -> None:
        """Test unknown manufacturer returns None."""
        filename = find_template("UNKNOWN", None)
        assert filename is None

    def test_wrong_product_name_returns_none(self) -> None:
        """Test wrong product name for specific template returns None."""
        # ACW requires specific product name
        filename = find_template("ACW", "Wrong Product")
        assert filename is None


class TestLoadTemplate:
    """Tests for load_template function."""

    def test_load_bundled_template(self) -> None:
        """Test loading bundled template."""
        template = load_template("itron_cyble_1_4.json")
        assert template is not None
        assert "0" in template  # Has sensor definitions

    def test_load_nonexistent_template(self) -> None:
        """Test loading non-existent template returns None."""
        template = load_template("nonexistent.json")
        assert template is None

    def test_template_caching(self) -> None:
        """Test templates are cached."""
        template1 = load_template("itron_cyble_1_4.json")
        template2 = load_template("itron_cyble_1_4.json")
        assert template1 is template2  # Same object (cached)

    def test_cache_clear(self) -> None:
        """Test cache clearing works."""
        template1 = load_template("itron_cyble_1_4.json")
        clear_cache()
        template2 = load_template("itron_cyble_1_4.json")
        # Should be equal but not same object after cache clear
        assert template1 == template2
        assert template1 is not template2


class TestGetTemplateForDevice:
    """Tests for get_template_for_device function."""

    def test_get_template_for_itron(self) -> None:
        """Test getting template for Itron device."""
        template = get_template_for_device("ACW", "Itron CYBLE M-Bus 1.4")
        assert template is not None
        assert "0" in template

    def test_get_template_for_unknown_device(self) -> None:
        """Test getting template for unknown device returns None."""
        template = get_template_for_device("UNKNOWN", None)
        assert template is None


# ============================================================================
# Template Content Validation Tests
# ============================================================================


class TestTemplateContent:
    """Tests for template content structure."""

    def test_itron_template_structure(self) -> None:
        """Test Itron template has expected structure."""
        template = load_template("itron_cyble_1_4.json")
        assert template is not None

        # Check sensor 0 (fabrication number)
        assert "0" in template
        assert "name" in template["0"]
        assert "value_template" in template["0"]

    def test_kamstrup_template_has_custom_sensors(self) -> None:
        """Test Kamstrup template has custom sensors."""
        template = load_template("kamstrup_multical_401.json")
        assert template is not None

        # Kamstrup has custom sensors for pulse inputs
        custom_keys = [k for k in template.keys() if k.startswith("custom-")]
        assert len(custom_keys) > 0

    def test_all_templates_have_required_fields(self) -> None:
        """Test all templates have required fields per sensor."""
        template_files = [
            "apt-mbus-na-1.json",
            "itron_cyble_1_4.json",
            "kamstrup_multical_401.json",
            "zri.json",
        ]

        for filename in template_files:
            template = load_template(filename)
            assert template is not None, f"Failed to load {filename}"

            for sensor_id, sensor_config in template.items():
                # All sensors should have name and value_template
                assert "name" in sensor_config, f"{filename}[{sensor_id}] missing 'name'"
                assert "value_template" in sensor_config, (
                    f"{filename}[{sensor_id}] missing 'value_template'"
                )


# ============================================================================
# User Template Tests
# ============================================================================


class TestUserTemplates:
    """Tests for user-defined templates."""

    @pytest.fixture
    def user_templates_dir(self, tmp_path: Path) -> Path:
        """Create temporary user templates directory."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        return templates_dir

    def test_user_template_takes_priority(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test user template overrides bundled template."""
        # Create user template with different content
        user_template = {
            "0": {
                "name": "User Defined Sensor",
                "value_template": "{{ value_json.user_sensor }}",
            }
        }
        (user_templates_dir / "itron_cyble_1_4.json").write_text(json.dumps(user_template))

        # Patch TEMPLATES_DIR to point to our temp dir
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        template = load_template("itron_cyble_1_4.json")
        assert template is not None
        assert template["0"]["name"] == "User Defined Sensor"

    def test_user_index_takes_priority(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test user index.json is checked first, bundled used as fallback."""
        # Create user index with custom manufacturer
        user_index = {
            "custom_device.json": {
                "Manufacturer": "XYZ",
                "ProductName": None,
            }
        }
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))

        # Create the template file
        user_template = {"0": {"name": "Custom", "value_template": "{{ value_json.x }}"}}
        (user_templates_dir / "custom_device.json").write_text(json.dumps(user_template))

        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        # Should find custom manufacturer
        filename = find_template("XYZ", None)
        assert filename == "custom_device.json"

        # Should still find bundled manufacturers when user index has no match
        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4")
        assert filename == "itron_cyble_1_4.json"

    def test_user_index_partial_fallback_to_bundled(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """User index with limited entries should still allow bundled matches."""
        user_index = {
            "custom_device.json": {
                "Manufacturer": "ZZZ",
                "ProductName": "OnlyOne",
            }
        }
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))
        (user_templates_dir / "custom_device.json").write_text(
            json.dumps({"0": {"name": "Only One", "value_template": "{{ value_json.a }}"}})
        )

        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        # User match still works
        filename = find_template("ZZZ", "OnlyOne")
        assert filename == "custom_device.json"

        # Bundled match still works when user index has no entry
        filename = find_template("KAM", "Kamstrup 382 (6850-005)")
        assert filename == "kamstrup_multical_401.json"

    def test_fallback_to_bundled_when_no_user_template(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test falls back to bundled when user template doesn't exist."""
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        # User dir exists but is empty, should fall back to bundled
        template = load_template("itron_cyble_1_4.json")
        assert template is not None
        # Should have bundled content
        assert "0" in template

    def test_new_device_template(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test adding template for new device not in bundled."""
        # Create user index that extends (replaces) bundled
        user_index = {
            "new_meter.json": {
                "Manufacturer": "NEW",
                "ProductName": "New Meter Model",
            }
        }
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))

        user_template = {"0": {"name": "New Sensor", "value_template": "{{ value_json.new }}"}}
        (user_templates_dir / "new_meter.json").write_text(json.dumps(user_template))

        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        template = get_template_for_device("NEW", "New Meter Model")
        assert template is not None
        assert template["0"]["name"] == "New Sensor"


# ============================================================================
# User Template Error Cases
# ============================================================================


class TestUserTemplateErrors:
    """Tests for user template error handling."""

    @pytest.fixture
    def user_templates_dir(self, tmp_path: Path) -> Path:
        """Create temporary user templates directory."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        return templates_dir

    def test_invalid_json_syntax(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test invalid JSON syntax raises JSONDecodeError."""
        (user_templates_dir / "invalid.json").write_text('{"0": {"name": "Test"')
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        with pytest.raises(json.JSONDecodeError):
            load_template("invalid.json")

    def test_empty_template_file(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test empty file raises JSONDecodeError."""
        (user_templates_dir / "empty.json").write_text("")
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        with pytest.raises(json.JSONDecodeError):
            load_template("empty.json")

    def test_array_instead_of_dict(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test JSON array instead of object."""
        (user_templates_dir / "array.json").write_text('[{"name": "Test"}]')
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        template = load_template("array.json")
        # Loads successfully but is a list, not dict
        assert isinstance(template, list)
        # Accessing as dict would fail
        with pytest.raises(TypeError):
            _ = template["0"]  # type: ignore[index]

    def test_string_instead_of_dict(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test JSON string instead of object."""
        (user_templates_dir / "string.json").write_text('"just a string"')
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        template = load_template("string.json")
        assert template == "just a string"
        # Accessing as dict would fail
        with pytest.raises(TypeError):
            _ = template["0"]  # type: ignore[index]

    def test_permission_error(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test file permission error."""
        template_file = user_templates_dir / "noperm.json"
        template_file.write_text('{"0": {"name": "Test"}}')
        template_file.chmod(0o000)

        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        try:
            with pytest.raises(PermissionError):
                load_template("noperm.json")
        finally:
            # Restore permissions for cleanup
            template_file.chmod(0o644)


class TestUserIndexErrors:
    """Tests for user index.json error handling."""

    @pytest.fixture
    def user_templates_dir(self, tmp_path: Path) -> Path:
        """Create temporary user templates directory."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        return templates_dir

    def test_invalid_json_in_index(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test invalid JSON in index raises JSONDecodeError."""
        (user_templates_dir / "index.json").write_text('{"template.json": {')
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        with pytest.raises(json.JSONDecodeError):
            find_template("ANY", None)

    def test_index_references_missing_template(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test index references template that doesn't exist."""
        user_index = {"missing.json": {"Manufacturer": "XXX", "ProductName": None}}
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        # find_template returns the filename
        filename = find_template("XXX", None)
        assert filename == "missing.json"

        # But load_template returns None (file doesn't exist)
        template = load_template("missing.json")
        assert template is None

    def test_invalid_match_criteria(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test invalid match criteria in index."""
        # Index with wrong key (NotManufacturer instead of Manufacturer)
        user_index = {"template.json": {"NotManufacturer": "XXX"}}
        (user_templates_dir / "index.json").write_text(json.dumps(user_index))
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        # Should never match (no "Manufacturer" key)
        filename = find_template("XXX", None)
        assert filename is None

    def test_empty_index(
        self,
        user_templates_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test empty index returns no matches."""
        (user_templates_dir / "index.json").write_text("{}")
        monkeypatch.setattr(templates, "TEMPLATES_DIR", user_templates_dir)
        clear_cache()

        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4")
        # Empty user index should fall back to bundled index
        assert filename == "itron_cyble_1_4.json"


# ============================================================================
# Cache Behavior Tests
# ============================================================================


class TestCacheBehavior:
    """Tests for template caching behavior."""

    def test_template_cached_after_first_load(self) -> None:
        """Test template is cached after first load."""
        clear_cache()
        template1 = load_template("itron_cyble_1_4.json")
        template2 = load_template("itron_cyble_1_4.json")
        assert template1 is template2

    def test_cache_cleared_properly(self) -> None:
        """Test cache is cleared properly."""
        template1 = load_template("itron_cyble_1_4.json")
        clear_cache()
        template2 = load_template("itron_cyble_1_4.json")
        assert template1 is not template2
        assert template1 == template2

    def test_index_cached_after_first_load(self) -> None:
        """Test index is cached after first load."""
        clear_cache()
        # First call loads index
        find_template("ACW", "Itron CYBLE M-Bus 1.4")
        # Second call uses cached index (we can't directly test this,
        # but we can verify it doesn't error)
        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4")
        assert filename == "itron_cyble_1_4.json"

    def test_index_cleared_with_cache(self) -> None:
        """Test index is cleared when cache is cleared."""
        find_template("ACW", "Itron CYBLE M-Bus 1.4")
        clear_cache()
        # Should reload index and still work
        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4")
        assert filename == "itron_cyble_1_4.json"


# ============================================================================
# Fixture Template Matching Tests
# ============================================================================


class TestFixtureTemplateMatching:
    """Tests that fixtures match expected templates."""

    def test_apator_fixture_template_match(self, apator_mbus_data: Any) -> None:
        """Test Apator fixture matches apt-mbus-na-1 template."""
        filename = find_template(
            apator_mbus_data.manufacturer,
            apator_mbus_data.slave_information.product_name,
        )
        assert filename == "apt-mbus-na-1.json"

    def test_itron_fixture_template_match(self, itron_mbus_data: Any) -> None:
        """Test Itron fixture matches itron_cyble_1_4 template."""
        filename = find_template(
            itron_mbus_data.manufacturer,
            itron_mbus_data.slave_information.product_name,
        )
        assert filename == "itron_cyble_1_4.json"

    def test_kamstrup_fixture_template_match(self, kamstrup_mbus_data: Any) -> None:
        """Test Kamstrup fixture matches kamstrup_multical_401 template."""
        filename = find_template(
            kamstrup_mbus_data.manufacturer,
            kamstrup_mbus_data.slave_information.product_name,
        )
        assert filename == "kamstrup_multical_401.json"

    def test_bmeters_fixture_template_match(self, bmeters_mbus_data: Any) -> None:
        """Test B Meters fixture matches zri template."""
        filename = find_template(
            bmeters_mbus_data.manufacturer,
            bmeters_mbus_data.slave_information.product_name,
        )
        assert filename == "zri.json"

    def test_zenner_fixture_template_match(self, zenner_mbus_data: Any) -> None:
        """Test Zenner fixture matches zri template."""
        filename = find_template(
            zenner_mbus_data.manufacturer,
            zenner_mbus_data.slave_information.product_name,
        )
        assert filename == "zri.json"


# ============================================================================
# No Index Found Tests
# ============================================================================


class TestNoIndexFound:
    """Tests for when no index is found."""

    def test_no_index_returns_empty_dict(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test no index returns empty dict."""
        empty_dir = tmp_path / "empty_templates"
        empty_dir.mkdir()

        # Patch both user and bundled paths to empty directories
        monkeypatch.setattr(templates, "TEMPLATES_DIR", empty_dir)
        monkeypatch.setattr(templates, "_get_bundled_templates_path", lambda: empty_dir)
        clear_cache()

        # Should return None for any manufacturer
        filename = find_template("ACW", "Itron CYBLE M-Bus 1.4")
        assert filename is None
