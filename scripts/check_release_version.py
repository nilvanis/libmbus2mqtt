"""Reject release tags whose PEP 440 version differs from the package version."""

from __future__ import annotations

import sys

from packaging.version import InvalidVersion, Version

from libmbus2mqtt._version import __version__


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("v"):
        raise SystemExit("Usage: check_release_version.py v<VERSION>")
    tag = sys.argv[1]
    try:
        matches = Version(tag[1:]) == Version(__version__)
    except InvalidVersion as exc:
        raise SystemExit(f"Invalid release version: {exc}") from None
    if not matches:
        raise SystemExit(f"Release tag {tag} does not match package version {__version__}")
    print(f"Release tag {tag} matches package version {__version__}")


if __name__ == "__main__":
    main()
