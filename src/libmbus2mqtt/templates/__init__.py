"""Home Assistant device templates."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from libmbus2mqtt.constants import TEMPLATES_DIR
from libmbus2mqtt.logging import get_logger

logger = get_logger("templates")

# Cache for loaded templates
_template_cache: dict[str, dict[str, Any]] = {}
_index_cache: dict[str, dict[str, str | None]] | None = None


def _get_bundled_templates_path() -> Path:
    """Get path to bundled templates."""
    return Path(resources.files("libmbus2mqtt") / "templates")  # type: ignore[arg-type]


def _load_index() -> dict[str, dict[str, str | None]]:
    """Load template index from bundled or user templates."""
    global _index_cache
    if _index_cache is not None:
        return _index_cache

    # Try user templates first
    user_index = TEMPLATES_DIR / "index.json"
    if user_index.exists():
        logger.debug(f"Loading template index from {user_index}")
        with user_index.open() as f:
            _index_cache = json.load(f)
            return _index_cache

    # Fall back to bundled templates
    bundled_index = _get_bundled_templates_path() / "index.json"
    if bundled_index.exists():
        logger.debug("Loading template index from bundled templates")
        with bundled_index.open() as f:
            _index_cache = json.load(f)
            return _index_cache

    logger.warning("No template index found")
    _index_cache = {}
    return _index_cache


def find_template(manufacturer: str, product_name: str | None) -> str | None:
    """
    Find matching template filename for a device.

    Args:
        manufacturer: Device manufacturer code
        product_name: Device product name (can be None)

    Returns:
        Template filename or None if no match
    """
    index = _load_index()

    for filename, match_criteria in index.items():
        if match_criteria.get("Manufacturer") != manufacturer:
            continue

        expected_product = match_criteria.get("ProductName")
        if expected_product is None or expected_product == product_name:
            logger.debug(f"Matched template {filename} for {manufacturer}/{product_name}")
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
    global _template_cache, _index_cache
    _template_cache = {}
    _index_cache = None
