"""CLI checks that do not require system changes or live hardware."""

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from libmbus2mqtt.cli import app
from libmbus2mqtt.config import AppConfig


def test_generated_config_enables_rotating_file_logs(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    runner = CliRunner()
    result = runner.invoke(app, ["config", "init", "--config", str(config_file)])
    assert result.exit_code == 0, result.output
    config = AppConfig.load(config_file)
    assert config.logs.file is None
    assert config.logs.save_to_file
    assert config.logs.max_size_mb == 10
    assert config.logs.backup_count == 5
    result = runner.invoke(app, ["config", "validate", "--config", str(config_file)])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("command", ["run", "scan"])
@pytest.mark.parametrize("source", ["default", "env", "flag"])
def test_data_directory_is_selected_by_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    source: str,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "data_dir: /ignored-yaml\nmbus:\n  device: /dev/simulated\nmqtt:\n  host: localhost\n"
    )
    if source == "default":
        monkeypatch.delenv("LIBMBUS2MQTT_DATA_DIR", raising=False)
        data_dir = Path("/var/lib/libmbus2mqtt")
    else:
        # The Docker image sets the variable; an explicit --data-dir still wins.
        monkeypatch.setenv("LIBMBUS2MQTT_DATA_DIR", str(tmp_path / "from-env"))
        data_dir = tmp_path / ("from-env" if source == "env" else "from-flag")
    setup_logging = MagicMock()
    run_daemon = MagicMock()
    interface = MagicMock()
    interface.return_value.scan.return_value = []
    check_data_dir = MagicMock()
    monkeypatch.setattr("libmbus2mqtt.logging.setup_logging", setup_logging)
    monkeypatch.setattr("libmbus2mqtt.main.run_daemon", run_daemon)
    monkeypatch.setattr("libmbus2mqtt.mbus.interface.MbusInterface", interface)
    monkeypatch.setattr("libmbus2mqtt.preflight.check_data_dir", check_data_dir)
    args = [command, "--config", str(config_file)]
    if source == "flag":
        args.extend(["--data-dir", str(data_dir)])

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 0, result.output
    setup_logging.assert_called_once()
    assert setup_logging.call_args.kwargs["default_log_file"] == data_dir / "log/libmbus2mqtt.log"
    assert setup_logging.call_args.kwargs["logs_config"].save_to_file
    if command == "run":
        check_data_dir.assert_called_once_with(data_dir)
        run_daemon.assert_called_once()
        assert run_daemon.call_args.kwargs["data_dir"] == data_dir
    else:
        check_data_dir.assert_not_called()
        interface.return_value.scan.assert_called_once()


def test_service_dry_run_uses_bundled_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from libmbus2mqtt import constants

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    unit_dir = tmp_path / "units"
    monkeypatch.setattr(constants, "SERVICE_CONFIG_DIR", config_dir)
    monkeypatch.setattr(constants, "SERVICE_DATA_DIR", data_dir)
    monkeypatch.setattr(constants, "SYSTEMD_SERVICE_DIR", unit_dir)
    monkeypatch.setattr("libmbus2mqtt.installer.find_executable", lambda: SYSTEM_EXECUTABLE)
    result = CliRunner().invoke(app, ["install", "--dry-run", "--yes"])
    assert result.exit_code == 0, result.output
    assert "bundled service" in result.output
    assert not config_dir.exists()
    assert not data_dir.exists()
    assert not unit_dir.exists()


SYSTEM_EXECUTABLE = Path("/opt/libmbus2mqtt/bin/libmbus2mqtt")


def _fake_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executable: Path = SYSTEM_EXECUTABLE
) -> tuple[MagicMock, MagicMock]:
    """Run `install` against temporary directories instead of the real system."""
    from libmbus2mqtt import constants, installer

    monkeypatch.setattr(constants, "SERVICE_CONFIG_DIR", tmp_path / "etc")
    monkeypatch.setattr(constants, "SERVICE_DATA_DIR", tmp_path / "var")
    monkeypatch.setattr(constants, "SYSTEMD_SERVICE_DIR", tmp_path / "units")
    (tmp_path / "units").mkdir()
    monkeypatch.setattr(installer, "require_root", lambda command: None)
    monkeypatch.setattr(installer, "user_exists", lambda name: True)
    monkeypatch.setattr(installer, "find_executable", lambda: executable)
    run_command = MagicMock()
    chown = MagicMock()
    monkeypatch.setattr(installer, "run_command", run_command)
    monkeypatch.setattr("shutil.chown", chown)
    return run_command, chown


def test_install_creates_private_config_and_unit_for_this_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_command, chown = _fake_system(tmp_path, monkeypatch)

    result = CliRunner().invoke(app, ["install", "--yes"])

    assert result.exit_code == 0, result.output
    config_file = tmp_path / "etc/config.yaml"
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    assert AppConfig.load(config_file).mqtt.host
    chown.assert_any_call(config_file, user="libmbus2mqtt")
    unit = (tmp_path / "units/libmbus2mqtt.service").read_text()
    assert f"ExecStart={SYSTEM_EXECUTABLE} run --config /etc/libmbus2mqtt/config.yaml" in unit
    run_command.assert_any_call(["systemctl", "enable", "libmbus2mqtt.service"], dry_run=False)
    assert "sudo systemctl start libmbus2mqtt.service" in result.output


def test_install_keeps_existing_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_system(tmp_path, monkeypatch)
    config_file = tmp_path / "etc/config.yaml"
    config_file.parent.mkdir()
    config_file.write_text("my settings\n")

    result = CliRunner().invoke(app, ["install", "--yes"])

    assert result.exit_code == 0, result.output
    assert config_file.read_text() == "my settings\n"
    assert "sudo systemctl restart libmbus2mqtt.service" in result.output


def test_install_refuses_executable_hidden_from_the_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_system(tmp_path, monkeypatch, Path("/home/pi/.local/bin/libmbus2mqtt"))

    result = CliRunner().invoke(app, ["install", "--yes"])

    assert result.exit_code == 1
    assert "ProtectHome" in result.output
    assert not (tmp_path / "etc").exists()


def test_config_path_can_come_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "from-env.yaml"
    config_file.write_text("mbus:\n  device: /dev/ttyUSB0\nmqtt:\n  host: localhost\n")
    monkeypatch.setenv("LIBMBUS2MQTT_CONFIG", str(config_file))

    result = CliRunner().invoke(app, ["config", "validate"])

    assert result.exit_code == 0, result.output
    assert str(config_file) in result.output.replace("\n", "")


def test_invalid_config_does_not_print_password(tmp_path: Path) -> None:
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("mbus:\n  device: /dev/ttyUSB0\nmqtt:\n  password: cli-secret-value\n")
    result = CliRunner().invoke(app, ["config", "validate", "--config", str(config_file)])
    assert result.exit_code == 1
    assert "cli-secret-value" not in result.output
    assert "host" in result.output


def test_config_init_creates_private_file(tmp_path: Path) -> None:
    runner = CliRunner()
    new_file = tmp_path / "new.yaml"
    existing_file = tmp_path / "existing.yaml"
    existing_file.write_text("old")
    existing_file.chmod(0o644)

    assert runner.invoke(app, ["config", "init", "--config", str(new_file)]).exit_code == 0
    result = runner.invoke(app, ["config", "init", "--config", str(existing_file), "--force"])
    assert result.exit_code == 0, result.output

    assert stat.S_IMODE(new_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(existing_file.stat().st_mode) == 0o600


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission checks")
def test_run_stops_with_clear_error_on_unwritable_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("mbus:\n  device: /dev/simulated\nmqtt:\n  host: localhost\n")
    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o555)
    run_daemon = MagicMock()
    monkeypatch.setattr("libmbus2mqtt.logging.setup_logging", MagicMock())
    monkeypatch.setattr("libmbus2mqtt.main.run_daemon", run_daemon)
    try:
        result = CliRunner().invoke(
            app, ["run", "--config", str(config_file), "--data-dir", str(data_dir)]
        )
    finally:
        data_dir.chmod(0o755)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "is not writable" in caplog.text
    run_daemon.assert_not_called()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission checks")
def test_config_init_reports_unwritable_location(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o555)
    try:
        result = CliRunner().invoke(
            app, ["config", "init", "--config", str(locked / "config.yaml")]
        )
    finally:
        locked.chmod(0o755)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Run it with sudo" in result.output
