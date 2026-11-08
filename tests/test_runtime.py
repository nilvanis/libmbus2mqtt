"""Daemon startup with real storage/templates and simulated hardware/MQTT."""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libmbus2mqtt.config import AppConfig, DeviceConfig, HomeAssistantConfig, MbusConfig, MqttConfig
from libmbus2mqtt.main import Daemon
from libmbus2mqtt.models.mbus import MbusData
from libmbus2mqtt.mqtt.client import MqttClient


def test_startup_polls_with_configured_storage_and_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, apator_mbus_data: MbusData
) -> None:
    data_dir = tmp_path / "runtime"
    templates_dir = data_dir / "templates"
    config = AppConfig(
        mbus=MbusConfig(device="/dev/simulated", autoscan=False, startup_delay=0),
        mqtt=MqttConfig(host="localhost"),
        homeassistant=HomeAssistantConfig(enabled=True),
        devices=[DeviceConfig(id=1)],
    )
    templates_dir.mkdir(parents=True)
    (templates_dir / "index.json").write_text(
        json.dumps({"custom.json": {"Manufacturer": "APA", "DataRecordCount": 12}})
    )
    (templates_dir / "custom.json").write_text(
        json.dumps(
            {
                str(i): {
                    "name": f"Record {i}",
                    "component": "sensor",
                    "value_template": "{{ value_json.custom_" + str(i) + " }}",
                }
                for i in range(12)
            }
        )
    )
    mbus = MagicMock()
    mbus.poll.return_value = apator_mbus_data
    mqtt = MagicMock()
    mqtt.base_topic = "libmbus2mqtt"
    daemon = Daemon(config, data_dir=data_dir)
    mqtt.connect.side_effect = daemon._on_mqtt_connect
    monkeypatch.setattr("libmbus2mqtt.main.MbusInterface", lambda **kwargs: mbus)
    monkeypatch.setattr("libmbus2mqtt.main.MqttClient", lambda config: mqtt)
    monkeypatch.setattr("signal.signal", lambda *args: None)
    monkeypatch.setattr(daemon, "_run_loop", daemon._poll_devices)

    daemon.start()

    assert (data_dir / "libmbus2mqtt.db").is_file()
    mqtt.connect.assert_called_once()
    mqtt.disconnect.assert_called_once()
    mqtt.publish_device_state.assert_called_once()
    state = mqtt.publish_device_state.call_args.args[1]
    assert state["custom_0"] == apator_mbus_data.get_record_value("0")
    assert daemon._state_store is not None
    assert daemon._state_store.list_active_device_snapshots()[0].state == state


@pytest.mark.parametrize(
    "payload, expected", [(" debug ", "DEBUG"), ("INFO", "INFO"), ("TRACE", None)]
)
def test_log_level_command_publishes_state_without_waiting_for_poll(
    minimal_app_config: AppConfig,
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
    expected: str | None,
) -> None:
    minimal_app_config.mqtt.base_topic = "test-meters"
    monkeypatch.setattr(MqttClient, "connect", lambda self: None)
    daemon = Daemon(minimal_app_config)
    daemon._init_mqtt()
    assert daemon._mqtt is not None
    publish = MagicMock(return_value=True)
    monkeypatch.setattr(daemon._mqtt, "publish", publish)
    root_logger = logging.getLogger()
    package_logger = logging.getLogger("libmbus2mqtt")
    original_levels = root_logger.level, package_logger.level
    try:
        package_logger.setLevel(logging.INFO)
        message = MagicMock(topic="test-meters/command/log_level", payload=payload.encode())
        daemon._mqtt._on_message(MagicMock(), None, message)

        if expected is None:
            publish.assert_not_called()
            assert package_logger.level == logging.INFO
        else:
            publish.assert_called_once()
            topic, state = publish.call_args.args
            assert topic == "test-meters/bridge/info"
            assert json.loads(state)["log_level"] == expected
            assert publish.call_args.kwargs["retain"] is True
            assert package_logger.level == getattr(logging, expected)
    finally:
        root_logger.setLevel(original_levels[0])
        package_logger.setLevel(original_levels[1])
