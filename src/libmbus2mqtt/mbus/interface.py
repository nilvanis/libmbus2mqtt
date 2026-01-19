"""M-Bus interface wrapper using libmbus CLI tools."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from libmbus2mqtt.constants import LIBMBUS_BINARIES, LIBMBUS_DEFAULT_INSTALL_PATH
from libmbus2mqtt.logging import get_logger

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
    ) -> None:
        self.device = device
        self.baudrate = baudrate
        self.libmbus_path = Path(libmbus_path)
        self._validate_libmbus()

    def _validate_libmbus(self) -> None:
        """Check if libmbus binaries are available."""
        for binary in LIBMBUS_BINARIES:
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

    def scan(self, timeout: int = 60) -> list[int]:
        """
        Scan for M-Bus devices.

        Returns:
            List of discovered device IDs.
        """
        logger.info(f"Scanning for M-Bus devices on {self.device}...")

        binary = self._get_binary_path("mbus-serial-scan")
        cmd = [binary, "-b", str(self.baudrate), self.device]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"Scan timed out after {timeout}s")
            return []
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return []

        # Parse output for device IDs
        devices: list[int] = []
        for line in result.stdout.splitlines():
            match = SCAN_PATTERN.search(line)
            if match:
                device_id = int(match.group(1))
                devices.append(device_id)
                logger.debug(f"Found device at address {device_id}")

        logger.info(f"Scan complete: {len(devices)} device(s) found")
        return devices

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

        binary = self._get_binary_path("mbus-serial-request-data")
        cmd = [binary, "-b", str(self.baudrate), self.device, str(device_id)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                logger.warning(f"Poll device {device_id} failed: {result.stderr}")
                return None

            return result.stdout

        except subprocess.TimeoutExpired:
            logger.warning(f"Poll device {device_id} timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Poll device {device_id} failed: {e}")
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
