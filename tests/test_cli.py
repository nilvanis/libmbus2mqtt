"""CLI checks that do not require system changes or live hardware."""

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
@pytest.mark.parametrize("custom_directory", [False, True])
def test_data_directory_is_selected_by_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    custom_directory: bool,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "data_dir: /ignored-yaml\nmbus:\n  device: /dev/simulated\nmqtt:\n  host: localhost\n"
    )
    monkeypatch.setenv("LIBMBUS2MQTT_DATA_DIR", "/ignored-env")
    setup_logging = MagicMock()
    run_daemon = MagicMock()
    interface = MagicMock()
    interface.return_value.scan.return_value = []
    monkeypatch.setattr("libmbus2mqtt.logging.setup_logging", setup_logging)
    monkeypatch.setattr("libmbus2mqtt.main.run_daemon", run_daemon)
    monkeypatch.setattr("libmbus2mqtt.mbus.interface.MbusInterface", interface)
    args = [command, "--config", str(config_file)]
    data_dir = tmp_path / "runtime" if custom_directory else Path("/data")
    if custom_directory:
        args.extend(["--data-dir", str(data_dir)])

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 0, result.output
    setup_logging.assert_called_once()
    assert setup_logging.call_args.kwargs["default_log_file"] == data_dir / "log/libmbus2mqtt.log"
    assert setup_logging.call_args.kwargs["logs_config"].save_to_file
    if command == "run":
        run_daemon.assert_called_once()
        assert run_daemon.call_args.kwargs["data_dir"] == data_dir
    else:
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
    result = CliRunner().invoke(app, ["install", "--dry-run", "--yes"])
    assert result.exit_code == 0, result.output
    assert "bundled service" in result.output
    assert not config_dir.exists()
    assert not data_dir.exists()
    assert not unit_dir.exists()


def test_invalid_config_does_not_print_password(tmp_path: Path) -> None:
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("mbus:\n  device: /dev/ttyUSB0\nmqtt:\n  password: cli-secret-value\n")
    result = CliRunner().invoke(app, ["config", "validate", "--config", str(config_file)])
    assert result.exit_code == 1
    assert "cli-secret-value" not in result.output
    assert "host" in result.output
