"""Daemon startup with real storage/templates and simulated hardware/MQTT."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libmbus2mqtt.config import AppConfig, DeviceConfig, HomeAssistantConfig, MbusConfig, MqttConfig
from libmbus2mqtt.main import Daemon
from libmbus2mqtt.models.mbus import MbusData


def test_startup_polls_with_configured_storage_and_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, apator_mbus_data: MbusData
) -> None:
    config = AppConfig(
        data_dir=tmp_path / "runtime",
        mbus=MbusConfig(device="/dev/simulated", autoscan=False, startup_delay=0),
        mqtt=MqttConfig(host="localhost"),
        homeassistant=HomeAssistantConfig(enabled=True),
        devices=[DeviceConfig(id=1)],
    )
    config.templates_dir.mkdir(parents=True)
    (config.templates_dir / "index.json").write_text(
        json.dumps({"custom.json": {"Manufacturer": "APA", "DataRecordCount": 12}})
    )
    (config.templates_dir / "custom.json").write_text(
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
    daemon = Daemon(config)
    mqtt.connect.side_effect = daemon._on_mqtt_connect
    monkeypatch.setattr("libmbus2mqtt.main.MbusInterface", lambda **kwargs: mbus)
    monkeypatch.setattr("libmbus2mqtt.main.MqttClient", lambda config: mqtt)
    monkeypatch.setattr("signal.signal", lambda *args: None)
    monkeypatch.setattr(daemon, "_run_loop", daemon._poll_devices)

    daemon.start()

    assert config.db_path.is_file()
    mqtt.connect.assert_called_once()
    mqtt.disconnect.assert_called_once()
    mqtt.publish_device_state.assert_called_once()
    state = mqtt.publish_device_state.call_args.args[1]
    assert state["custom_0"] == apator_mbus_data.get_record_value("0")
    assert daemon._state_store is not None
    assert daemon._state_store.list_active_device_snapshots()[0].state == state
