"""Helpers that prepare the systemd service."""

import sys
from pathlib import Path

import pytest

from libmbus2mqtt import installer


def test_render_service_points_exec_start_at_executable() -> None:
    unit = installer.render_service(Path("/opt/libmbus2mqtt/bin/libmbus2mqtt"))

    exec_lines = [line for line in unit.splitlines() if line.startswith("ExecStart=")]
    assert exec_lines == [
        "ExecStart=/opt/libmbus2mqtt/bin/libmbus2mqtt run "
        "--config /etc/libmbus2mqtt/config.yaml --data-dir /var/lib/libmbus2mqtt"
    ]
    assert "ProtectHome=yes" in unit


@pytest.mark.parametrize(
    "executable, problem",
    [
        ("/opt/libmbus2mqtt/bin/libmbus2mqtt", None),
        ("/usr/local/bin/libmbus2mqtt", None),
        ("/home/pi/.local/bin/libmbus2mqtt", "ProtectHome"),
        ("/root/venv/bin/libmbus2mqtt", "ProtectHome"),
        ("/opt/my tools/libmbus2mqtt", "whitespace"),
    ],
)
def test_check_service_executable(executable: str, problem: str | None) -> None:
    result = installer.check_service_executable(Path(executable))
    if problem is None:
        assert result is None
    else:
        assert result is not None and problem in result


def test_check_service_executable_follows_symlinks(tmp_path: Path) -> None:
    # A /usr/local/bin symlink into a home directory is still hidden from the service.
    link = tmp_path / "libmbus2mqtt"
    link.symlink_to("/home/pi/.local/bin/libmbus2mqtt")
    result = installer.check_service_executable(link)
    assert result is not None and "ProtectHome" in result


def test_find_executable_prefers_the_running_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = tmp_path / "libmbus2mqtt"
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    monkeypatch.setattr(sys, "argv", [str(command), "install"])

    assert installer.find_executable() == command


def test_find_executable_fails_without_a_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "python"), "-m", "libmbus2mqtt"])
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)

    with pytest.raises(FileNotFoundError, match="Cannot locate"):
        installer.find_executable()


def test_libmbus_pin_is_a_release_commit() -> None:
    repo, commit = installer.get_libmbus_source()
    assert repo == "https://github.com/rscada/libmbus.git"
    assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)
    assert installer.get_libmbus_version().count(".") == 2
