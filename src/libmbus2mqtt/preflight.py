"""Startup checks for data directory and serial device access.

Permission problems otherwise surface as low-level errors (SQLite's "unable to
open database file", failing libmbus calls) that do not say who is running the
process or who owns the path. These checks fail early with that information.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from libmbus2mqtt.constants import DEFAULT_DB_FILE
from libmbus2mqtt.logging import get_logger
from libmbus2mqtt.mbus.utils import parse_mbus_device

if TYPE_CHECKING:
    from libmbus2mqtt.config import MqttTlsConfig

logger = get_logger("preflight")

_DATA_DIR_HINT = (
    "In Docker, start the container without `user:` and set PUID/PGID so the entrypoint "
    "fixes ownership, or chown the mounted host directory to the uid above. For the "
    "systemd service, check the ownership of its StateDirectory."
)


class PreflightError(Exception):
    """Startup cannot continue; the message tells the operator how to fix it."""


def process_identity() -> str:
    """Describe the credentials file access is checked against."""
    uid, gid = os.getuid(), os.getgid()
    extra = sorted(set(os.getgroups()) - {gid})
    groups = ",".join(str(group) for group in extra) or "none"
    return f"uid={uid} gid={gid} supplementary groups={groups}"


def describe_path(path: Path) -> str:
    """Show a path with its numeric owner and permission bits."""
    try:
        st = path.stat()
    except OSError:
        return str(path)
    return f"{path} (owner {st.st_uid}:{st.st_gid}, mode {stat.S_IMODE(st.st_mode):04o})"


def check_data_dir(data_dir: Path) -> None:
    """Ensure the data directory and the state database are writable."""
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PreflightError(
            f"Cannot create data directory {data_dir}: {exc.strerror or exc}. "
            f"Running as {process_identity()}. {_DATA_DIR_HINT}"
        ) from None

    if not os.access(data_dir, os.W_OK | os.X_OK):
        raise PreflightError(
            f"Data directory {describe_path(data_dir)} is not writable. "
            f"Running as {process_identity()}. {_DATA_DIR_HINT}"
        )

    db_file = data_dir / DEFAULT_DB_FILE.name
    if db_file.exists() and not os.access(db_file, os.R_OK | os.W_OK):
        raise PreflightError(
            f"State database {describe_path(db_file)} is not readable and writable. "
            f"Running as {process_identity()}. {_DATA_DIR_HINT}"
        )


def check_tls_files(tls: MqttTlsConfig) -> None:
    """Ensure the configured TLS certificate and key files can be read."""
    if not tls.enabled:
        return
    for option, path in (
        ("ca_certs", tls.ca_certs),
        ("certfile", tls.certfile),
        ("keyfile", tls.keyfile),
    ):
        if path is None:
            continue
        if not path.is_file():
            raise PreflightError(f"mqtt.tls.{option}: {path} does not exist or is not a file.")
        if not os.access(path, os.R_OK):
            raise PreflightError(
                f"mqtt.tls.{option}: {describe_path(path)} is not readable. "
                f"Running as {process_identity()}. In Docker, keep the files inside the "
                "data directory (e.g. data/config/certs/) so the entrypoint hands them to "
                "PUID:PGID; natively, make them readable by the service user."
            )


def check_serial_device(device: str) -> None:
    """Ensure a configured serial device can be opened for reading and writing."""
    if parse_mbus_device(device).type != "serial":
        return

    path = Path(device)
    if not path.exists():
        logger.warning("Serial device %s does not exist; polling fails until it appears", device)
        return
    if os.access(path, os.R_OK | os.W_OK):
        return

    try:
        group = str(path.stat().st_gid)
    except OSError:
        group = "<device group>"
    raise PreflightError(
        f"No read/write access to serial device {describe_path(path)}. "
        f"Running as {process_identity()}. Give the process group {group}: in Docker the "
        f'entrypoint adds it for mapped devices, with `user:` add `group_add: ["{group}"]`; '
        f"for a native install add the service user to that group."
    )
