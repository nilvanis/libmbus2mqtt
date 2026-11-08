"""CLI checks that do not require system changes or live hardware."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from libmbus2mqtt.cli import app
from libmbus2mqtt.config import AppConfig


def test_generated_config_uses_runtime_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.yaml"
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("LIBMBUS2MQTT_DATA_DIR", str(runtime))
    runner = CliRunner()
    result = runner.invoke(app, ["config", "init", "--config", str(config_file)])
    assert result.exit_code == 0, result.output
    config = AppConfig.load(config_file)
    assert config.log_file == runtime / "log/libmbus2mqtt.log"
    assert not config.logs.save_to_file
    result = runner.invoke(app, ["config", "validate", "--config", str(config_file)])
    assert result.exit_code == 0, result.output


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
