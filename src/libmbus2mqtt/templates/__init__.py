"""Home Assistant device templates."""

from __future__ import annotations

import json
from typing import cast
from importlib import resources
from pathlib import Path
from typing import Any

from libmbus2mqtt.constants import TEMPLATES_DIR
from libmbus2mqtt.logging import get_logger

logger = get_logger("templates")

# Cache for loaded templates
_template_cache: dict[str, dict[str, Any]] = {}
_user_index_cache: dict[str, dict[str, str | None]] | None = None
_bundled_index_cache: dict[str, dict[str, str | None]] | None = None


def _get_bundled_templates_path() -> Path:
    """Get path to bundled templates."""
    return Path(resources.files("libmbus2mqtt") / "templates")  # type: ignore[arg-type]


def _load_index_file(path: Path) -> dict[str, dict[str, str | None]]:
    """Load an index file from the given path."""
    with path.open() as f:
        return cast(dict[str, dict[str, str | None]], json.load(f))


def _get_user_index() -> dict[str, dict[str, str | None]]:
    """Load user template index (if present)."""
    global _user_index_cache
    if _user_index_cache is not None:
        return _user_index_cache

    user_index = TEMPLATES_DIR / "index.json"
    if user_index.exists():
        logger.debug(f"Loading template index from {user_index}")
        _user_index_cache = _load_index_file(user_index)
    else:
        _user_index_cache = {}
    return _user_index_cache


def _get_bundled_index() -> dict[str, dict[str, str | None]]:
    """Load bundled template index (if present)."""
    global _bundled_index_cache
    if _bundled_index_cache is not None:
        return _bundled_index_cache

    bundled_index = _get_bundled_templates_path() / "index.json"
    if bundled_index.exists():
        logger.debug("Loading template index from bundled templates")
        _bundled_index_cache = _load_index_file(bundled_index)
    else:
        _bundled_index_cache = {}
    return _bundled_index_cache


def find_template(manufacturer: str, product_name: str | None) -> str | None:
    """
    Find matching template filename for a device.

    Args:
        manufacturer: Device manufacturer code
        product_name: Device product name (can be None)

    Returns:
        Template filename or None if no match
    """
    # Try user index first
    user_index = _get_user_index()
    for filename, match_criteria in user_index.items():
        if match_criteria.get("Manufacturer") != manufacturer:
            continue

        expected_product = match_criteria.get("ProductName")
        if expected_product is None or expected_product == product_name:
            logger.debug(f"Matched user template {filename} for {manufacturer}/{product_name}")
            return filename

    # Fall back to bundled index
    bundled_index = _get_bundled_index()

    for filename, match_criteria in bundled_index.items():
        if match_criteria.get("Manufacturer") != manufacturer:
            continue

        expected_product = match_criteria.get("ProductName")
        if expected_product is None or expected_product == product_name:
            logger.debug(f"Matched bundled template {filename} for {manufacturer}/{product_name}")
            return filename

    logger.warning(f"No template found for {manufacturer}/{product_name}")
    return None


def load_template(filename: str) -> dict[str, Any] | None:
    """
    Load a template by filename.

    Checks user templates directory first, then bundled templates.

    Args:
        filename: Template filename (e.g., "itron_cyble_1_4.json")

    Returns:
        Template dict or None if not found
    """
    if filename in _template_cache:
        return _template_cache[filename]

    # Try user templates first
    user_template = TEMPLATES_DIR / filename
    if user_template.exists():
        logger.debug(f"Loading template from {user_template}")
        with user_template.open() as f:
            template: dict[str, Any] = json.load(f)
            _template_cache[filename] = template
            return template

    # Fall back to bundled templates
    bundled_template = _get_bundled_templates_path() / filename
    if bundled_template.exists():
        logger.debug(f"Loading template from bundled: {filename}")
        with bundled_template.open() as f:
            template = json.load(f)
            _template_cache[filename] = template
            return template

    logger.warning(f"Template not found: {filename}")
    return None


def get_template_for_device(
    manufacturer: str, product_name: str | None
) -> dict[str, Any] | None:
    """
    Get template for a device by manufacturer and product name.

    Args:
        manufacturer: Device manufacturer code
        product_name: Device product name (can be None)

    Returns:
        Template dict or None if no match
    """
    filename = find_template(manufacturer, product_name)
    if filename is None:
        return None
    return load_template(filename)


def clear_cache() -> None:
    """Clear template caches."""
    global _template_cache, _user_index_cache, _bundled_index_cache
    _template_cache = {}
    _user_index_cache = None
    _bundled_index_cache = None
