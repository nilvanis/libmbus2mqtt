"""Tests for MQTT client wrapper."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from libmbus2mqtt.config import MqttConfig
from libmbus2mqtt.constants import (
    APP_NAME,
    TOPIC_BRIDGE_STATE,
    TOPIC_DEVICE_AVAILABILITY,
    TOPIC_DEVICE_STATE,
)
from libmbus2mqtt.mqtt.client import MqttClient

# ============================================================================
# MqttClient Properties Tests
# ============================================================================


class TestMqttClientProperties:
    """Tests for MqttClient properties."""

    @pytest.fixture
    def mqtt_config(self) -> MqttConfig:
        """Create MQTT config for testing."""
        return MqttConfig(
            host="localhost",
            port=1883,
            username="user",
            password="pass",
            base_topic="test_topic",
        )

    def test_base_topic_from_config(self, mqtt_config: MqttConfig) -> None:
        """Test base_topic returns config value."""
        client = MqttClient(mqtt_config)
        assert client.base_topic == "test_topic"

    def test_is_connected_default_false(self, mqtt_config: MqttConfig) -> None:
        """Test is_connected defaults to False."""
        client = MqttClient(mqtt_config)
        assert client.is_connected is False

    def test_client_id_uses_config(self, mqtt_config: MqttConfig) -> None:
        """Test client ID uses config when provided."""
        mqtt_config.client_id = "my-client-id"
        client = MqttClient(mqtt_config)
        assert client._get_client_id() == "my-client-id"

    def test_client_id_auto_generated(self, mqtt_config: MqttConfig) -> None:
        """Test client ID auto-generated when not in config."""
        mqtt_config.client_id = None
        client = MqttClient(mqtt_config)
        client_id = client._get_client_id()
        assert client_id.startswith(APP_NAME)


# ============================================================================
# MqttClient Connection Tests
# ============================================================================


class TestMqttClientConnection:
    """Tests for MqttClient connection methods."""

    @pytest.fixture
    def mqtt_config(self) -> MqttConfig:
        """Create MQTT config for testing."""
        return MqttConfig(host="localhost", port=1883)

    @pytest.fixture
    def mock_paho_client(self) -> MagicMock:
        """Create mock paho MQTT client."""
        mock = MagicMock()
        mock.connect.return_value = 0
        mock.publish.return_value = MagicMock(rc=0)
        return mock

    @patch("libmbus2mqtt.mqtt.client.mqtt.Client")
    def test_connect_creates_client(
        self,
        mock_client_class: MagicMock,
        mqtt_config: MqttConfig,
    ) -> None:
        """Test connect creates paho client."""
        mock_instance = MagicMock()
        mock_instance.connect.return_value = 0
        mock_client_class.return_value = mock_instance

        # Mock the Event.wait to return True immediately
        with patch("threading.Event.wait", return_value=True):
            client = MqttClient(mqtt_config)
            client.connect()

        mock_client_class.assert_called_once()
        mock_instance.connect.assert_called_once()

    @patch("libmbus2mqtt.mqtt.client.mqtt.Client")
    def test_connect_sets_credentials(
        self,
        mock_client_class: MagicMock,
    ) -> None:
        """Test connect sets credentials when provided."""
        mock_instance = MagicMock()
        mock_instance.connect.return_value = 0
        mock_client_class.return_value = mock_instance

        config = MqttConfig(
            host="localhost",
            username="user",
            password="pass",
        )

        with patch("threading.Event.wait", return_value=True):
            client = MqttClient(config)
            client.connect()

        mock_instance.username_pw_set.assert_called_once_with("user", "pass")

    @patch("libmbus2mqtt.mqtt.client.mqtt.Client")
    def test_connect_sets_last_will(
        self,
        mock_client_class: MagicMock,
        mqtt_config: MqttConfig,
    ) -> None:
        """Test connect sets last will message."""
        mock_instance = MagicMock()
        mock_instance.connect.return_value = 0
        mock_client_class.return_value = mock_instance

        with patch("threading.Event.wait", return_value=True):
            client = MqttClient(mqtt_config)
            client.connect()

        # Should set will for bridge state topic
        will_topic = TOPIC_BRIDGE_STATE.format(base=client.base_topic)
        mock_instance.will_set.assert_called_once_with(
            will_topic, "offline", qos=1, retain=True
        )

    @patch("libmbus2mqtt.mqtt.client.mqtt.Client")
    def test_connect_timeout_raises_error(
        self,
        mock_client_class: MagicMock,
        mqtt_config: MqttConfig,
    ) -> None:
        """Test connection timeout raises ConnectionError."""
        mock_instance = MagicMock()
        mock_instance.connect.return_value = 0
        mock_client_class.return_value = mock_instance

        # Mock wait to return False (timeout)
        with patch("threading.Event.wait", return_value=False):
            client = MqttClient(mqtt_config)
            with pytest.raises(ConnectionError, match="MQTT connection timeout"):
                client.connect()

    @patch("libmbus2mqtt.mqtt.client.mqtt.Client")
    def test_disconnect_publishes_offline(
        self,
        mock_client_class: MagicMock,
        mqtt_config: MqttConfig,
    ) -> None:
        """Test disconnect publishes offline status."""
        mock_instance = MagicMock()
        mock_instance.connect.return_value = 0
        mock_instance.publish.return_value = MagicMock(rc=0)
        mock_client_class.return_value = mock_instance

        with patch("threading.Event.wait", return_value=True):
            client = MqttClient(mqtt_config)
            client.connect()

        # Simulate connected state
        client._connected.set()

        client.disconnect()

        # Should have published offline
        calls = mock_instance.publish.call_args_list
        offline_calls = [c for c in calls if "offline" in str(c)]
        assert len(offline_calls) > 0


# ============================================================================
# MqttClient Publish Tests
# ============================================================================


class TestMqttClientPublish:
    """Tests for MqttClient publish methods."""

    @pytest.fixture
    def mqtt_config(self) -> MqttConfig:
        """Create MQTT config for testing."""
        return MqttConfig(host="localhost", base_topic="test")

    @pytest.fixture
    def connected_client(self, mqtt_config: MqttConfig) -> MqttClient:
        """Create a mock-connected client."""
        client = MqttClient(mqtt_config)
        client._client = MagicMock()
        client._client.publish.return_value = MagicMock(rc=0)
        client._connected.set()
        return client

    def test_publish_string_payload(self, connected_client: MqttClient) -> None:
        """Test publishing string payload."""
        result = connected_client.publish("test/topic", "hello")
        assert result is True
        connected_client._client.publish.assert_called_once()

    def test_publish_dict_payload(self, connected_client: MqttClient) -> None:
        """Test publishing dict payload converts to JSON."""
        payload = {"key": "value"}
        result = connected_client.publish("test/topic", payload)
        assert result is True

        # Should have been called with JSON string
        call_args = connected_client._client.publish.call_args
        assert call_args[0][1] == json.dumps(payload)

    def test_publish_with_retain(self, connected_client: MqttClient) -> None:
        """Test publishing with retain flag."""
        connected_client.publish("test/topic", "hello", retain=True)

        call_args = connected_client._client.publish.call_args
        assert call_args[1]["retain"] is True

    def test_publish_with_custom_qos(self, connected_client: MqttClient) -> None:
        """Test publishing with custom QoS."""
        connected_client.publish("test/topic", "hello", qos=2)

        call_args = connected_client._client.publish.call_args
        assert call_args[1]["qos"] == 2

    def test_publish_when_not_connected_returns_false(
        self, mqtt_config: MqttConfig
    ) -> None:
        """Test publish returns False when not connected."""
        client = MqttClient(mqtt_config)
        result = client.publish("test/topic", "hello")
        assert result is False

    def test_publish_failure_returns_false(self, connected_client: MqttClient) -> None:
        """Test publish failure returns False."""
        connected_client._client.publish.return_value = MagicMock(rc=1)  # Error
        result = connected_client.publish("test/topic", "hello")
        assert result is False


class TestMqttClientPublishHelpers:
    """Tests for MqttClient publish helper methods."""

    @pytest.fixture
    def connected_client(self) -> MqttClient:
        """Create a mock-connected client."""
        config = MqttConfig(host="localhost", base_topic="test")
        client = MqttClient(config)
        client._client = MagicMock()
        client._client.publish.return_value = MagicMock(rc=0)
        client._connected.set()
        return client

    def test_publish_bridge_state(self, connected_client: MqttClient) -> None:
        """Test publish_bridge_state publishes to correct topic."""
        connected_client.publish_bridge_state("online")

        call_args = connected_client._client.publish.call_args
        expected_topic = TOPIC_BRIDGE_STATE.format(base="test")
        assert call_args[0][0] == expected_topic
        assert call_args[0][1] == "online"
        assert call_args[1]["retain"] is True

    def test_publish_device_state(self, connected_client: MqttClient) -> None:
        """Test publish_device_state publishes to correct topic."""
        state = {"key": "value"}
        connected_client.publish_device_state("device123", state)

        call_args = connected_client._client.publish.call_args
        expected_topic = TOPIC_DEVICE_STATE.format(base="test", device_id="device123")
        assert call_args[0][0] == expected_topic
        assert call_args[1]["retain"] is True

    def test_publish_device_availability(self, connected_client: MqttClient) -> None:
        """Test publish_device_availability publishes to correct topic."""
        connected_client.publish_device_availability("device123", "online")

        call_args = connected_client._client.publish.call_args
        expected_topic = TOPIC_DEVICE_AVAILABILITY.format(
            base="test", device_id="device123"
        )
        assert call_args[0][0] == expected_topic
        assert call_args[0][1] == "online"
        assert call_args[1]["retain"] is True

    def test_publish_ha_discovery(self, connected_client: MqttClient) -> None:
        """Test publish_ha_discovery publishes to correct topic."""
        config = {"name": "Test Sensor"}
        connected_client.publish_ha_discovery(
            component="sensor",
            object_id="test_sensor",
            config=config,
            discovery_prefix="homeassistant",
        )

        call_args = connected_client._client.publish.call_args
        assert call_args[0][0] == "homeassistant/sensor/test_sensor/config"
        assert call_args[1]["retain"] is True

    def test_publish_ha_discovery_custom_prefix(
        self, connected_client: MqttClient
    ) -> None:
        """Test publish_ha_discovery with custom prefix."""
        config = {"name": "Test Sensor"}
        connected_client.publish_ha_discovery(
            component="sensor",
            object_id="test_sensor",
            config=config,
            discovery_prefix="custom",
        )

        call_args = connected_client._client.publish.call_args
        assert call_args[0][0] == "custom/sensor/test_sensor/config"

    def test_remove_ha_discovery(self, connected_client: MqttClient) -> None:
        """Test remove_ha_discovery publishes empty payload."""
        connected_client.remove_ha_discovery(
            component="sensor",
            object_id="test_sensor",
            discovery_prefix="homeassistant",
        )

        call_args = connected_client._client.publish.call_args
        assert call_args[0][0] == "homeassistant/sensor/test_sensor/config"
        assert call_args[0][1] == ""
        assert call_args[1]["retain"] is True


# ============================================================================
# MqttClient Callback Tests
# ============================================================================


class TestMqttClientCallbacks:
    """Tests for MqttClient callback registration."""

    @pytest.fixture
    def client(self) -> MqttClient:
        """Create MQTT client for testing."""
        config = MqttConfig(host="localhost", base_topic="test")
        return MqttClient(config)

    def test_register_command_callback(self, client: MqttClient) -> None:
        """Test registering command callback."""
        callback = MagicMock()
        client.register_command_callback("{base}/command/test", callback)

        # Should be stored with formatted topic
        assert "test/command/test" in client._command_callbacks
        assert client._command_callbacks["test/command/test"] == callback

    def test_on_connect_callback_setter(self, client: MqttClient) -> None:
        """Test setting on_connect callback."""
        callback = MagicMock()
        client.on_connect(callback)
        assert client._on_connect_callback == callback

    def test_on_disconnect_callback_setter(self, client: MqttClient) -> None:
        """Test setting on_disconnect callback."""
        callback = MagicMock()
        client.on_disconnect(callback)
        assert client._on_disconnect_callback == callback

    def test_on_message_calls_command_callback(self, client: MqttClient) -> None:
        """Test _on_message calls registered command callback."""
        callback = MagicMock()
        client.register_command_callback("{base}/command/test", callback)

        # Create mock message
        mock_message = MagicMock()
        mock_message.topic = "test/command/test"
        mock_message.payload = b"payload_data"

        # Call _on_message
        client._on_message(MagicMock(), None, mock_message)

        callback.assert_called_once_with("test/command/test", "payload_data")

    def test_on_message_handles_callback_error(self, client: MqttClient) -> None:
        """Test _on_message handles callback errors gracefully."""
        callback = MagicMock(side_effect=ValueError("Test error"))
        client.register_command_callback("{base}/command/test", callback)

        mock_message = MagicMock()
        mock_message.topic = "test/command/test"
        mock_message.payload = b"payload"

        # Should not raise
        client._on_message(MagicMock(), None, mock_message)

        # Callback was called but error was caught
        callback.assert_called_once()


# ============================================================================
# MqttClient Internal Callback Tests
# ============================================================================


class TestMqttClientInternalCallbacks:
    """Tests for MqttClient internal paho callbacks."""

    @pytest.fixture
    def client(self) -> MqttClient:
        """Create MQTT client for testing."""
        config = MqttConfig(host="localhost", base_topic="test")
        client = MqttClient(config)
        client._client = MagicMock()
        client._client.publish.return_value = MagicMock(rc=0)
        return client

    def test_on_connect_success_sets_connected(self, client: MqttClient) -> None:
        """Test _on_connect with success sets connected flag."""
        mock_reason_code = MagicMock()
        mock_reason_code.value = 0

        client._on_connect(MagicMock(), None, None, mock_reason_code, None)

        assert client.is_connected is True

    def test_on_connect_success_publishes_online(self, client: MqttClient) -> None:
        """Test _on_connect publishes online status."""
        mock_reason_code = MagicMock()
        mock_reason_code.value = 0

        client._on_connect(MagicMock(), None, None, mock_reason_code, None)

        # Should have published online
        calls = client._client.publish.call_args_list
        online_calls = [c for c in calls if "online" in str(c)]
        assert len(online_calls) > 0

    def test_on_connect_success_calls_user_callback(self, client: MqttClient) -> None:
        """Test _on_connect calls user callback on success."""
        user_callback = MagicMock()
        client.on_connect(user_callback)

        mock_reason_code = MagicMock()
        mock_reason_code.value = 0

        client._on_connect(MagicMock(), None, None, mock_reason_code, None)

        user_callback.assert_called_once()

    def test_on_connect_failure_does_not_set_connected(
        self, client: MqttClient
    ) -> None:
        """Test _on_connect failure does not set connected flag."""
        mock_reason_code = MagicMock()
        mock_reason_code.value = 1  # Error

        client._on_connect(MagicMock(), None, None, mock_reason_code, None)

        assert client.is_connected is False

    def test_on_disconnect_clears_connected(self, client: MqttClient) -> None:
        """Test _on_disconnect clears connected flag."""
        client._connected.set()
        client._stopping = True  # Intentional disconnect

        client._on_disconnect(MagicMock(), None, None, 0, None)

        assert client.is_connected is False

    def test_on_disconnect_calls_user_callback_on_unexpected(
        self, client: MqttClient
    ) -> None:
        """Test _on_disconnect calls user callback on unexpected disconnect."""
        user_callback = MagicMock()
        client.on_disconnect(user_callback)
        client._connected.set()
        client._stopping = False  # Unexpected disconnect

        client._on_disconnect(MagicMock(), None, None, 0, None)

        user_callback.assert_called_once()

    def test_on_disconnect_does_not_call_callback_on_intentional(
        self, client: MqttClient
    ) -> None:
        """Test _on_disconnect does not call callback on intentional disconnect."""
        user_callback = MagicMock()
        client.on_disconnect(user_callback)
        client._connected.set()
        client._stopping = True  # Intentional disconnect

        client._on_disconnect(MagicMock(), None, None, 0, None)

        user_callback.assert_not_called()
