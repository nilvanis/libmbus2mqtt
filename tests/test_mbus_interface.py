"""Tests for M-Bus interface wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libmbus2mqtt.mbus.interface import SCAN_PATTERN, MbusInterface

# ============================================================================
# Scan Pattern Tests
# ============================================================================


class TestScanPattern:
    """Tests for SCAN_PATTERN regex."""

    def test_matches_valid_output(self) -> None:
        """Test pattern matches valid scan output."""
        line = "Found a M-Bus device at address 1"
        match = SCAN_PATTERN.search(line)
        assert match is not None
        assert match.group(1) == "1"

    def test_matches_multi_digit_address(self) -> None:
        """Test pattern matches multi-digit addresses."""
        line = "Found a M-Bus device at address 123"
        match = SCAN_PATTERN.search(line)
        assert match is not None
        assert match.group(1) == "123"

    def test_does_not_match_invalid_line(self) -> None:
        """Test pattern does not match invalid lines."""
        line = "Some other output"
        match = SCAN_PATTERN.search(line)
        assert match is None

    def test_extracts_address_as_string(self) -> None:
        """Test extracted address is a string (needs int conversion)."""
        line = "Found a M-Bus device at address 42"
        match = SCAN_PATTERN.search(line)
        assert match is not None
        assert isinstance(match.group(1), str)
        assert int(match.group(1)) == 42


# ============================================================================
# MbusInterface Initialization Tests
# ============================================================================


class TestMbusInterfaceInit:
    """Tests for MbusInterface initialization."""

    @pytest.fixture
    def mock_libmbus_path(self, tmp_path: Path) -> Path:
        """Create mock libmbus binaries."""
        for binary in ["mbus-serial-scan", "mbus-serial-request-data"]:
            (tmp_path / binary).touch()
        return tmp_path

    def test_init_with_valid_binaries(self, mock_libmbus_path: Path) -> None:
        """Test initialization with valid binary path."""
        interface = MbusInterface(
            device="/dev/ttyUSB0",
            baudrate=2400,
            libmbus_path=mock_libmbus_path,
        )
        assert interface.device == "/dev/ttyUSB0"
        assert interface.baudrate == 2400
        assert interface.libmbus_path == mock_libmbus_path

    def test_init_validates_binaries_in_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test initialization checks PATH if binaries not in libmbus_path."""
        # Empty directory (no binaries)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Mock subprocess.run for 'which' command to succeed
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        interface = MbusInterface(
            device="/dev/ttyUSB0",
            libmbus_path=empty_dir,
        )
        assert interface.device == "/dev/ttyUSB0"

    def test_init_raises_if_binaries_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test initialization raises if binaries not found."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Mock subprocess.run for 'which' command to fail
        def mock_run(*args: object, **kwargs: object) -> None:
            raise subprocess.CalledProcessError(1, "which")

        monkeypatch.setattr(subprocess, "run", mock_run)

        with pytest.raises(FileNotFoundError, match="libmbus binary not found"):
            MbusInterface(device="/dev/ttyUSB0", libmbus_path=empty_dir)

    def test_default_baudrate(self, mock_libmbus_path: Path) -> None:
        """Test default baudrate is 2400."""
        interface = MbusInterface(
            device="/dev/ttyUSB0",
            libmbus_path=mock_libmbus_path,
        )
        assert interface.baudrate == 2400


# ============================================================================
# MbusInterface Scan Tests
# ============================================================================


class TestMbusInterfaceScan:
    """Tests for MbusInterface scan method."""

    @pytest.fixture
    def mock_libmbus_path(self, tmp_path: Path) -> Path:
        """Create mock libmbus binaries."""
        for binary in ["mbus-serial-scan", "mbus-serial-request-data"]:
            (tmp_path / binary).touch()
        return tmp_path

    @pytest.fixture
    def interface(self, mock_libmbus_path: Path) -> MbusInterface:
        """Create MbusInterface instance."""
        return MbusInterface(
            device="/dev/ttyUSB0",
            baudrate=2400,
            libmbus_path=mock_libmbus_path,
        )

    def test_scan_returns_discovered_devices(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test scan returns list of discovered device IDs."""
        scan_output = """
Found a M-Bus device at address 1
Found a M-Bus device at address 5
Found a M-Bus device at address 10
"""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout=scan_output, stderr="", returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        devices = interface.scan()
        assert devices == [1, 5, 10]

    def test_scan_returns_empty_on_no_devices(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test scan returns empty list when no devices found."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        devices = interface.scan()
        assert devices == []

    def test_scan_returns_empty_on_timeout(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test scan returns empty list on timeout."""

        def mock_run(*args: object, **kwargs: object) -> None:
            raise subprocess.TimeoutExpired("cmd", 60)

        monkeypatch.setattr(subprocess, "run", mock_run)

        devices = interface.scan(timeout=60)
        assert devices == []

    def test_scan_returns_empty_on_error(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test scan returns empty list on general error."""

        def mock_run(*args: object, **kwargs: object) -> None:
            raise OSError("Device error")

        monkeypatch.setattr(subprocess, "run", mock_run)

        devices = interface.scan()
        assert devices == []

    def test_scan_uses_correct_command(
        self,
        interface: MbusInterface,
        mock_libmbus_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test scan uses correct command arguments."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        interface.scan(timeout=30)

        call_args = mock_run.call_args
        cmd = call_args[0][0]

        # Should include binary, -b baudrate, device
        assert "mbus-serial-scan" in cmd[0]
        assert "-b" in cmd
        assert "2400" in cmd
        assert "/dev/ttyUSB0" in cmd

        # Should include timeout
        assert call_args[1]["timeout"] == 30


# ============================================================================
# MbusInterface Poll Raw Tests
# ============================================================================


class TestMbusInterfacePollRaw:
    """Tests for MbusInterface poll_raw method."""

    @pytest.fixture
    def mock_libmbus_path(self, tmp_path: Path) -> Path:
        """Create mock libmbus binaries."""
        for binary in ["mbus-serial-scan", "mbus-serial-request-data"]:
            (tmp_path / binary).touch()
        return tmp_path

    @pytest.fixture
    def interface(self, mock_libmbus_path: Path) -> MbusInterface:
        """Create MbusInterface instance."""
        return MbusInterface(
            device="/dev/ttyUSB0",
            baudrate=2400,
            libmbus_path=mock_libmbus_path,
        )

    def test_poll_raw_returns_xml(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
        apator_xml: str,
    ) -> None:
        """Test poll_raw returns XML string."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout=apator_xml, stderr="", returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = interface.poll_raw(1)
        assert result == apator_xml

    def test_poll_raw_returns_none_on_error(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test poll_raw returns None on error."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout="", stderr="Error", returncode=1)
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = interface.poll_raw(1)
        assert result is None

    def test_poll_raw_returns_none_on_timeout(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test poll_raw returns None on timeout."""

        def mock_run(*args: object, **kwargs: object) -> None:
            raise subprocess.TimeoutExpired("cmd", 10)

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = interface.poll_raw(1, timeout=10)
        assert result is None

    def test_poll_raw_returns_none_on_exception(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test poll_raw returns None on general exception."""

        def mock_run(*args: object, **kwargs: object) -> None:
            raise OSError("Device error")

        monkeypatch.setattr(subprocess, "run", mock_run)

        result = interface.poll_raw(1)
        assert result is None

    def test_poll_raw_uses_correct_command(
        self,
        interface: MbusInterface,
        mock_libmbus_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test poll_raw uses correct command arguments."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        interface.poll_raw(42, timeout=15)

        call_args = mock_run.call_args
        cmd = call_args[0][0]

        # Should include binary, -b baudrate, device, device_id
        assert "mbus-serial-request-data" in cmd[0]
        assert "-b" in cmd
        assert "2400" in cmd
        assert "/dev/ttyUSB0" in cmd
        assert "42" in cmd

        # Should include timeout
        assert call_args[1]["timeout"] == 15

    def test_poll_raw_warns_on_device_id_0(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test poll_raw logs warning for device ID 0."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        interface.poll_raw(0)
        assert "device ID 0" in caplog.text


# ============================================================================
# MbusInterface Poll Tests
# ============================================================================


class TestMbusInterfacePoll:
    """Tests for MbusInterface poll method."""

    @pytest.fixture
    def mock_libmbus_path(self, tmp_path: Path) -> Path:
        """Create mock libmbus binaries."""
        for binary in ["mbus-serial-scan", "mbus-serial-request-data"]:
            (tmp_path / binary).touch()
        return tmp_path

    @pytest.fixture
    def interface(self, mock_libmbus_path: Path) -> MbusInterface:
        """Create MbusInterface instance."""
        return MbusInterface(
            device="/dev/ttyUSB0",
            baudrate=2400,
            libmbus_path=mock_libmbus_path,
        )

    def test_poll_returns_parsed_data(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
        apator_xml: str,
    ) -> None:
        """Test poll returns parsed MbusData."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout=apator_xml, stderr="", returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = interface.poll(1)

        assert result is not None
        assert result.device_id == "67434"
        assert result.manufacturer == "APA"

    def test_poll_returns_none_on_raw_failure(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test poll returns None when poll_raw fails."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(stdout="", stderr="Error", returncode=1)
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = interface.poll(1)
        assert result is None

    def test_poll_returns_none_on_parse_error(
        self,
        interface: MbusInterface,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test poll returns None when parsing fails."""
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="invalid xml", stderr="", returncode=0
        )
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = interface.poll(1)
        assert result is None


# ============================================================================
# MbusInterface Binary Path Tests
# ============================================================================


class TestMbusInterfaceBinaryPath:
    """Tests for _get_binary_path method."""

    @pytest.fixture
    def mock_libmbus_path(self, tmp_path: Path) -> Path:
        """Create mock libmbus binaries."""
        for binary in ["mbus-serial-scan", "mbus-serial-request-data"]:
            (tmp_path / binary).touch()
        return tmp_path

    def test_returns_full_path_when_exists(self, mock_libmbus_path: Path) -> None:
        """Test returns full path when binary exists in libmbus_path."""
        interface = MbusInterface(
            device="/dev/ttyUSB0",
            libmbus_path=mock_libmbus_path,
        )

        path = interface._get_binary_path("mbus-serial-scan")
        assert path == str(mock_libmbus_path / "mbus-serial-scan")

    def test_returns_name_only_when_not_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns binary name only when not in libmbus_path."""
        # Create directory without binaries
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Mock 'which' to succeed (so validation passes)
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)
        monkeypatch.setattr(subprocess, "run", mock_run)

        interface = MbusInterface(
            device="/dev/ttyUSB0",
            libmbus_path=empty_dir,
        )

        # Should return just the binary name (assumes in PATH)
        path = interface._get_binary_path("mbus-serial-scan")
        assert path == "mbus-serial-scan"
