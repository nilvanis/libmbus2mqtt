"""Release tags must agree with the version shipped in the package."""

import subprocess
import sys
from pathlib import Path

import pytest

from libmbus2mqtt import __version__


@pytest.mark.parametrize("tag", [f"v{__version__}", "v999.0.0", "invalid", "vnot-a-version"])
def test_release_version_gate(tag: str) -> None:
    script = Path(__file__).resolve().parent.parent / "scripts/check_release_version.py"
    result = subprocess.run([sys.executable, str(script), tag], capture_output=True, text=True)
    assert (result.returncode == 0) == (tag == f"v{__version__}")
    assert result.stdout or result.stderr
