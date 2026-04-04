"""Home Assistant device templates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, cast

from libmbus2mqtt.constants import TEMPLATES_DIR
from libmbus2mqtt.logging import get_logger

logger = get_logger("templates")

# Cache for loaded templates
_template_cache: dict[str, dict[str, Any]] = {}
_user_index_cache: dict[str, dict[str, str | int | None]] | None = None
_bundled_index_cache: dict[str, dict[str, str | int | None]] | None = None


@dataclass(frozen=True)
class TemplateSelection:
    """Resolved template metadata."""

    filename: str | None
    template: dict[str, Any] | None
    mode: str
    source: str


def _get_bundled_templates_path() -> Path:
    """Get path to bundled templates."""
    return Path(resources.files("libmbus2mqtt") / "templates")  # type: ignore[arg-type]


def _load_index_file(path: Path) -> dict[str, dict[str, str | int | None]]:
    """Load an index file from the given path."""
    with path.open() as f:
        return cast(dict[str, dict[str, str | int | None]], json.load(f))


def _get_user_index() -> dict[str, dict[str, str | int | None]]:
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


def _get_bundled_index() -> dict[str, dict[str, str | int | None]]:
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


def count_template_records(template: dict[str, Any]) -> int:
    """Count numeric DataRecord mappings in a template."""
    return sum(1 for key in template if key.isdigit())


def _template_matches_record_count(
    filename: str,
    template: dict[str, Any],
    data_record_count: int | None,
) -> bool:
    """Validate a template against the current XML DataRecord count."""
    if data_record_count is None:
        return True

    template_count = count_template_records(template)
    if template_count == data_record_count:
        return True

    logger.warning(
        "Ignoring template %s: template defines %s numeric DataRecords, payload has %s",
        filename,
        template_count,
        data_record_count,
    )
    return False


def _find_template_in_index(
    index: dict[str, dict[str, str | int | None]],
    manufacturer: str,
    product_name: str | None,
    data_record_count: int | None,
) -> str | None:
    normalized_product = product_name or None
    exact_matches: list[str] = []
    fallback_matches: list[str] = []
    counted_fallback_matches: list[str] = []

    for filename, match_criteria in index.items():
        if match_criteria.get("Manufacturer") != manufacturer:
            continue

        expected_product = cast(str | None, match_criteria.get("ProductName"))
        if expected_product is not None and expected_product != normalized_product:
            continue

        expected_count = match_criteria.get("DataRecordCount")
        if expected_count is None:
            fallback_matches.append(filename)
            continue

        if not isinstance(expected_count, int):
            logger.warning(
                "Ignoring template %s with invalid DataRecordCount=%r", filename, expected_count
            )
            continue

        if data_record_count is None:
            counted_fallback_matches.append(filename)
            continue

        if expected_count == data_record_count:
            exact_matches.append(filename)

    if len(exact_matches) > 1:
        logger.warning(
            "Ambiguous template index entries for %s/%s with DataRecordCount=%s: %s",
            manufacturer,
            normalized_product,
            data_record_count,
            exact_matches,
        )
    if len(fallback_matches) > 1:
        logger.warning(
            "Ambiguous fallback template index entries for %s/%s: %s",
            manufacturer,
            normalized_product,
            fallback_matches,
        )
    if len(counted_fallback_matches) > 1:
        logger.warning(
            "Ambiguous counted fallback template index entries for %s/%s: %s",
            manufacturer,
            normalized_product,
            counted_fallback_matches,
        )

    if exact_matches:
        return exact_matches[0]
    if fallback_matches:
        return fallback_matches[0]
    if counted_fallback_matches:
        return counted_fallback_matches[0]
    return None


def find_template(
    manufacturer: str,
    product_name: str | None,
    data_record_count: int | None = None,
) -> str | None:
    """
    Find matching template filename for a device.

    Args:
        manufacturer: Device manufacturer code
        product_name: Device product name (can be None)
        data_record_count: Number of DataRecord items in the XML payload

    Returns:
        Template filename or None if no match
    """
    user_match = _find_template_in_index(
        _get_user_index(),
        manufacturer,
        product_name,
        data_record_count,
    )
    if user_match is not None:
        logger.debug(
            "Matched user template %s for %s/%s (DataRecordCount=%s)",
            user_match,
            manufacturer,
            product_name,
            data_record_count,
        )
        return user_match

    bundled_match = _find_template_in_index(
        _get_bundled_index(),
        manufacturer,
        product_name,
        data_record_count,
    )
    if bundled_match is not None:
        logger.debug(
            "Matched bundled template %s for %s/%s (DataRecordCount=%s)",
            bundled_match,
            manufacturer,
            product_name,
            data_record_count,
        )
        return bundled_match

    logger.warning(
        "No template found for %s/%s (DataRecordCount=%s)",
        manufacturer,
        product_name,
        data_record_count,
    )
    return None


def load_template(filename: str) -> dict[str, Any] | None:
    """
    Load a template by filename.

    Checks user templates directory first, then bundled templates.

    Args:
        filename: Template filename (e.g., "itron_cyble_1_4-dr8.json")

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
    manufacturer: str,
    product_name: str | None,
    data_record_count: int | None = None,
) -> dict[str, Any] | None:
    """
    Get template for a device by manufacturer and product name.

    Args:
        manufacturer: Device manufacturer code
        product_name: Device product name (can be None)
        data_record_count: Number of DataRecord items in the XML payload

    Returns:
        Template dict or None if no match
    """
    selection = resolve_template(
        manufacturer=manufacturer,
        product_name=product_name,
        data_record_count=data_record_count,
    )
    return selection.template


def resolve_template(
    *,
    manufacturer: str | None,
    product_name: str | None,
    data_record_count: int | None,
    explicit_filename: str | None = None,
) -> TemplateSelection:
    """Resolve the template to use for a device."""
    if explicit_filename:
        template = load_template(explicit_filename)
        if isinstance(template, dict):
            if not _template_matches_record_count(explicit_filename, template, data_record_count):
                logger.warning(
                    "Explicit template %s does not match payload DataRecordCount=%s",
                    explicit_filename,
                    data_record_count,
                )
            return TemplateSelection(
                filename=explicit_filename,
                template=template,
                mode="explicit",
                source="explicit",
            )
        logger.warning(
            "Explicit template %s could not be loaded, using generic discovery", explicit_filename
        )
        return TemplateSelection(filename=None, template=None, mode="generic", source="generic")

    if manufacturer is None:
        return TemplateSelection(filename=None, template=None, mode="generic", source="generic")

    user_match = _find_template_in_index(
        _get_user_index(),
        manufacturer,
        product_name,
        data_record_count,
    )
    if user_match is not None:
        template = load_template(user_match)
        if isinstance(template, dict) and _template_matches_record_count(
            user_match,
            template,
            data_record_count,
        ):
            return TemplateSelection(
                filename=user_match,
                template=template,
                mode="auto",
                source="user_index",
            )

    bundled_match = _find_template_in_index(
        _get_bundled_index(),
        manufacturer,
        product_name,
        data_record_count,
    )
    if bundled_match is not None:
        template = load_template(bundled_match)
        if isinstance(template, dict) and _template_matches_record_count(
            bundled_match,
            template,
            data_record_count,
        ):
            return TemplateSelection(
                filename=bundled_match,
                template=template,
                mode="auto",
                source="bundled_index",
            )

    return TemplateSelection(filename=None, template=None, mode="generic", source="generic")


def clear_cache() -> None:
    """Clear template caches."""
    global _template_cache, _user_index_cache, _bundled_index_cache
    _template_cache = {}
    _user_index_cache = None
    _bundled_index_cache = None
