"""Startup access checks for storage and serial devices."""

import os
from pathlib import Path

import pytest

from libmbus2mqtt.preflight import PreflightError, check_data_dir, check_serial_device

needs_non_root = pytest.mark.skipif(
    os.geteuid() == 0, reason="root bypasses file permission checks"
)


def test_missing_data_dir_is_created(tmp_path: Path) -> None:
    data_dir = tmp_path / "nested" / "data"
    check_data_dir(data_dir)
    assert data_dir.is_dir()


@needs_non_root
def test_read_only_data_dir_names_identity_and_owner(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o555)
    try:
        with pytest.raises(PreflightError) as exc:
            check_data_dir(data_dir)
    finally:
        data_dir.chmod(0o755)

    message = str(exc.value)
    assert f"uid={os.getuid()} gid={os.getgid()}" in message
    assert f"owner {os.getuid()}:{os.getgid()}, mode 0555" in message
    assert "PUID/PGID" in message


@needs_non_root
def test_uncreatable_data_dir(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o555)
    try:
        with pytest.raises(PreflightError, match="Cannot create data directory"):
            check_data_dir(parent / "data")
    finally:
        parent.chmod(0o755)


@needs_non_root
def test_read_only_database_is_reported(tmp_path: Path) -> None:
    (tmp_path / "libmbus2mqtt.db").touch(mode=0o444)
    with pytest.raises(PreflightError, match="State database"):
        check_data_dir(tmp_path)


def test_tcp_endpoint_skips_device_check() -> None:
    check_serial_device("192.168.1.10:9999")


def test_missing_serial_device_only_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    check_serial_device(str(tmp_path / "ttyUSB9"))
    assert "does not exist" in caplog.text


@needs_non_root
def test_inaccessible_serial_device_suggests_its_group(tmp_path: Path) -> None:
    device = tmp_path / "ttyUSB0"
    device.touch(mode=0o000)
    with pytest.raises(PreflightError) as exc:
        check_serial_device(str(device))
    assert f'group_add: ["{device.stat().st_gid}"]' in str(exc.value)


def test_accessible_serial_device_passes(tmp_path: Path) -> None:
    device = tmp_path / "ttyUSB0"
    device.touch(mode=0o600)
    check_serial_device(str(device))
