"""Tests for bridge state publishing."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from libmbus2mqtt.mqtt.bridge import BridgeInfo


class TestBridgeInfo:
    """Tests for BridgeInfo payload generation."""

    def test_get_state_includes_optional_scan_fields(self) -> None:
        mqtt_client = MagicMock()
        mqtt_client.base_topic = "libmbus2mqtt"
        bridge_info = BridgeInfo(mqtt_client)

        state = bridge_info.get_state()

        assert "last_scan" in state
        assert "last_poll_duration_ms" in state
        assert state["last_scan"] is None
        assert state["last_poll_duration_ms"] is None

    def test_set_last_scan_interprets_naive_datetime_as_system_local_time(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mqtt_client = MagicMock()
        mqtt_client.base_topic = "libmbus2mqtt"
        bridge_info = BridgeInfo(mqtt_client)

        if not hasattr(time, "tzset"):
            pytest.skip("time.tzset() is required for this test")

        original_tz = os.environ.get("TZ")
        try:
            monkeypatch.setenv("TZ", "Europe/Warsaw")
            time.tzset()

            bridge_info.set_last_scan(datetime(2026, 4, 5, 12, 30, 0))
        finally:
            if original_tz is None:
                monkeypatch.delenv("TZ", raising=False)
            else:
                monkeypatch.setenv("TZ", original_tz)
            time.tzset()

        assert bridge_info.get_state()["last_scan"] == "2026-04-05T10:30:00+00:00"

    def test_publish_serializes_null_optional_fields(self) -> None:
        mqtt_client = MagicMock()
        mqtt_client.base_topic = "libmbus2mqtt"
        mqtt_client.publish.return_value = True
        bridge_info = BridgeInfo(mqtt_client)
        bridge_info.set_last_scan(datetime(2026, 4, 5, 12, 30, 0, tzinfo=UTC))

        bridge_info.publish()

        mqtt_client.publish.assert_called_once()
        topic, payload = mqtt_client.publish.call_args.args[:2]
        state = json.loads(payload)
        assert topic == "libmbus2mqtt/bridge/info"
        assert state["discovered_devices"] == 0
        assert state["online_devices"] == 0
        assert state["poll_interval"] == 60
        assert state["last_scan"] == "2026-04-05T12:30:00+00:00"
        assert state["last_poll_duration_ms"] is None
        assert isinstance(state["uptime"], str)
        assert isinstance(state["log_level"], str)
        assert isinstance(state["version"], str)
