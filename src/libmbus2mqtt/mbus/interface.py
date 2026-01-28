"""M-Bus interface wrapper using libmbus CLI tools."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from libmbus2mqtt.constants import (
    LIBMBUS_DEFAULT_INSTALL_PATH,
    LIBMBUS_SERIAL_BINARIES,
    LIBMBUS_TCP_BINARIES,
    MBUS_DEFAULT_RETRY_COUNT,
    MBUS_DEFAULT_RETRY_DELAY,
    MBUS_DEFAULT_SCAN_TIMEOUT,
)
from libmbus2mqtt.logging import get_logger
from libmbus2mqtt.mbus.utils import MbusEndpoint, parse_mbus_device

if TYPE_CHECKING:
    from libmbus2mqtt.models.mbus import MbusData

logger = get_logger("mbus.interface")

# Regex pattern to extract device IDs from scan output
SCAN_PATTERN = re.compile(r"Found a M-Bus device at address (\d+)")


class MbusInterface:
    """Interface to M-Bus devices via libmbus CLI tools."""

    def __init__(
        self,
        device: str,
        baudrate: int = 2400,
        libmbus_path: Path | str = LIBMBUS_DEFAULT_INSTALL_PATH,
        retry_count: int = MBUS_DEFAULT_RETRY_COUNT,
        retry_delay: int = MBUS_DEFAULT_RETRY_DELAY,
    ) -> None:
        self.endpoint: MbusEndpoint = parse_mbus_device(device)
        self.device = device
        self.baudrate = baudrate
        self.libmbus_path = Path(libmbus_path)
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self._validate_libmbus()

    def _validate_libmbus(self) -> None:
        """Check if required libmbus binaries are available for the endpoint type."""
        binaries = LIBMBUS_TCP_BINARIES if self.endpoint.type == "tcp" else LIBMBUS_SERIAL_BINARIES

        for binary in binaries:
            binary_path = self.libmbus_path / binary
            if not binary_path.exists():
                # Try in PATH
                try:
                    subprocess.run(
                        ["which", binary],
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError:
                    raise FileNotFoundError(
                        f"libmbus binary not found: {binary}. "
                        f"Run 'libmbus2mqtt libmbus install' to install."
                    ) from None

    def _get_binary_path(self, binary: str) -> str:
        """Get the path to a libmbus binary."""
        binary_path = self.libmbus_path / binary
        if binary_path.exists():
            return str(binary_path)
        return binary  # Assume it's in PATH

    def _build_scan_cmd(self) -> list[str]:
        """Build the command list for scanning based on endpoint type."""
        if self.endpoint.type == "tcp":
            binary = self._get_binary_path("mbus-tcp-scan")
            return [binary, self.endpoint.host or "", str(self.endpoint.port or "")]

        binary = self._get_binary_path("mbus-serial-scan")
        return [binary, "-b", str(self.baudrate), self.device]

    def scan(self, timeout: int = MBUS_DEFAULT_SCAN_TIMEOUT) -> list[int]:
        """
        Scan for M-Bus devices.

        Returns:
            List of discovered device IDs.
        """
        logger.info(f"Scanning for M-Bus devices on {self.device} ({self.endpoint.type})...")

        cmd = self._build_scan_cmd()

        last_error: Exception | None = None

        for attempt in range(self.retry_count + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                if result.returncode != 0:
                    last_error = RuntimeError(result.stderr or "scan failed")
                    logger.warning(
                        "Scan attempt %s failed (rc=%s): %s",
                        attempt + 1,
                        result.returncode,
                        result.stderr.strip(),
                    )
                else:
                    devices: list[int] = []
                    for line in result.stdout.splitlines():
                        match = SCAN_PATTERN.search(line)
                        if match:
                            device_id = int(match.group(1))
                            devices.append(device_id)
                            logger.debug(f"Found device at address {device_id}")

                    logger.info(f"Scan complete: {len(devices)} device(s) found")
                    return devices

            except subprocess.TimeoutExpired as e:
                last_error = e
                logger.warning(
                    "Scan attempt %s timed out after %ss",
                    attempt + 1,
                    timeout,
                )
            except Exception as e:  # pragma: no cover - defensive
                last_error = e
                logger.error(f"Scan attempt {attempt + 1} failed: {e}")

            if attempt < self.retry_count:
                logger.debug(
                    "Retrying scan in %ss (%s/%s)",
                    self.retry_delay,
                    attempt + 1,
                    self.retry_count,
                )
                if self.retry_delay > 0:
                    time.sleep(self.retry_delay)

        logger.error("Scan failed after %s attempt(s): %s", self.retry_count + 1, last_error)
        return []

    def _build_poll_cmd(self, device_id: int) -> list[str]:
        """Build the command list for polling based on endpoint type."""
        if self.endpoint.type == "tcp":
            binary = self._get_binary_path("mbus-tcp-request-data")
            return [binary, self.endpoint.host or "", str(self.endpoint.port or ""), str(device_id)]

        binary = self._get_binary_path("mbus-serial-request-data")
        return [binary, "-b", str(self.baudrate), self.device, str(device_id)]

    def poll_raw(self, device_id: int, timeout: int = 10) -> str | None:
        """
        Poll a device for raw XML data.

        Args:
            device_id: M-Bus device address
            timeout: Command timeout in seconds

        Returns:
            XML response string or None on failure.
        """
        logger.debug(f"Polling device {device_id}...")

        if device_id == 0:
            logger.warning("Polling device ID 0 (default M-Bus address)")

        cmd = self._build_poll_cmd(device_id)

        last_error: Exception | None = None

        for attempt in range(self.retry_count + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                if result.returncode != 0:
                    last_error = RuntimeError(result.stderr or "poll failed")
                    logger.warning(
                        "Poll attempt %s for device %s failed (rc=%s): %s",
                        attempt + 1,
                        device_id,
                        result.returncode,
                        result.stderr.strip(),
                    )
                else:
                    return result.stdout

            except subprocess.TimeoutExpired as e:
                last_error = e
                logger.warning(
                    "Poll attempt %s for device %s timed out after %ss",
                    attempt + 1,
                    device_id,
                    timeout,
                )
            except Exception as e:  # pragma: no cover - defensive
                last_error = e
                logger.error(f"Poll attempt {attempt + 1} for device {device_id} failed: {e}")

            if attempt < self.retry_count:
                logger.debug(
                    "Retrying poll for device %s in %ss (%s/%s)",
                    device_id,
                    self.retry_delay,
                    attempt + 1,
                    self.retry_count,
                )
                if self.retry_delay > 0:
                    time.sleep(self.retry_delay)

        logger.warning(
            "Polling device %s failed after %s attempt(s): %s",
            device_id,
            self.retry_count + 1,
            last_error,
        )
        return None

    def poll(self, device_id: int, timeout: int = 10) -> MbusData | None:
        """
        Poll a device and parse the response.

        Args:
            device_id: M-Bus device address
            timeout: Command timeout in seconds

        Returns:
            Parsed MbusData or None on failure.
        """
        from libmbus2mqtt.mbus.parser import MbusParseError, parse_xml

        xml_data = self.poll_raw(device_id, timeout)
        if xml_data is None:
            return None

        try:
            return parse_xml(xml_data)
        except MbusParseError as e:
            logger.error(f"Failed to parse response from device {device_id}: {e}")
            return None
