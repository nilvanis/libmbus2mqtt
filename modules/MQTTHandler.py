import re
import json
import logging
import platform
import paho.mqtt.client as mqtt

import modules.Libmbus as Libmbus

from uuid import uuid4


log = logging.getLogger(__name__)

class Client:
    def __init__(self, *, host, port, username, password, base_topic='libmbus2mqtt', custom_topic=False):
        self.FLAG_ERROR = False
        self.ha_registered = False
        self.ha_status_topic = None
        self.ha_republish = False

        self.MQTT_CLIENTID = f"{platform.node()}-{str(uuid4()).split('-')[-1]}"
        try:
            self.MQTT_HOST = host
            self.MQTT_PORT = port
            self.MQTT_USERNAME = username
            self.MQTT_PASSWORD = password
            self.BASE_TOPIC = base_topic
            self.CUSTOM_TOPIC = custom_topic
        except Exception as e:
            self.FLAG_ERROR = True
            log.error(f"MQTT configuration is invalid!")
            log.exception(e)
            return
        
        self.configure()

    def configure(self):
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.MQTT_CLIENTID)
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_connect_fail = self._on_connect_fail
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_subscribe = self._on_subscribe
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.username_pw_set(self.MQTT_USERNAME, self.MQTT_PASSWORD)

    @property
    def IS_CONNECTED(self):
        return self.mqtt_client.is_connected()
    
    def connect(self, homeassistant=False):
        if homeassistant:
            self.mqtt_client.will_set(f"{self.BASE_TOPIC}/status", "offline", qos=2, retain=True)
        log.info(f"MQTT client ID: {self.MQTT_CLIENTID}")
        log.info(f"Connecting to MQTT broker: {self.MQTT_HOST}:{self.MQTT_PORT}")
        self.mqtt_client.connect(self.MQTT_HOST, self.MQTT_PORT, 60)
        self.mqtt_client.loop_start()

    def subscribe(self, *topics: str):
        if self.FLAG_ERROR:
            return
        for topic in topics:
            log.debug(f"Subscribing to {topic}")
            self.mqtt_client.subscribe(topic)

    def publish(self, device: Libmbus.Device, *, homeassistant=False):
        if self.FLAG_ERROR:
            return
        object_id = device.mbus_data['SlaveInformation']['Id']
        if homeassistant:
            topic_status = f"{self.BASE_TOPIC}/device/{object_id}/status"
            topic_state = f"{self.BASE_TOPIC}/device/{object_id}/state"
            payload = device.homeassistant_get_data()
            if device.availability.update:
                log.info(f"Publishing Home Assistant MQTT status for Device ID: '{device.device_id}. Status: '{device.availability.status}'")
                self.mqtt_client.publish(topic_status, device.availability.status, qos=2, retain=True)

        else: 
            if self.CUSTOM_TOPIC:
                topic_state = f"{self.CUSTOM_TOPIC}/{object_id}"
            else:
                topic_state = f"{self.BASE_TOPIC}/{object_id}"
            payload = json.dumps(device.mbus_data)

        log.debug(f"Publishing data to {topic_state}")
        self.mqtt_client.publish(topic_state, payload, qos=2)

    def ha_register(self, ha_config: dict):
        '''
        Method to subscribe to Home Assistant MQTT status message
        '''
        self.discovery_prefix = ha_config['discovery_prefix']
        self.ha_status_topic = f"{self.discovery_prefix}/status"
        self.subscribe(self.ha_status_topic)
        self.ha_registered = True

    def ha_device_register(self, device: Libmbus.Device, *, ha_config: dict, L2M_VERSION: str = ''):
        '''
        Method to register a device in Home Assistant via MQTT discovery.
        Device data and components template must be provided by Libmbus.Device object.
        '''
        if self.FLAG_ERROR:
            return
        
        if not self.ha_registered:
            self.ha_register(ha_config)

        object_id = re.sub(r'[^a-zA-Z0-9_-]', '_', device.mbus_data['SlaveInformation']['Id']) # [a-zA-Z0-9_-] are only allowed in HA MQTT discovery object_id
        discovery_topic = f"{self.discovery_prefix}/device/{object_id}/config"

        payload = {
            "device": {
                "identifiers"   : device.identifier,
                "name"          : device.name,
                "manufacturer"  : device.manufacturer,
                "model"         : device.model,
                "model_id"      : device.model_id,
                "sw_version"    : device.sw_version,
                "serial_number" : device.serial_number
            },
            "origin": {
                "name": "libmbus2mqtt",
                "sw_version": L2M_VERSION
            },
            "components": device.homeassistant_template,
            "state_topic": f"{self.BASE_TOPIC}/device/{object_id}/state",
            "availability": [
                {
                    "topic": f"{self.BASE_TOPIC}/status"
                },
                {
                    "topic": f"{self.BASE_TOPIC}/device/{object_id}/status" 
                }
            ],
            "availability_mode": "all",
            "qos": 2
        }
        
        msg_info = self.mqtt_client.publish(discovery_topic, json.dumps(payload), qos=2)
        return msg_info

    def _on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties):
        log.info(f"Connected.")
        log.debug(f'''Details:
                Flags: {flags}
                Userdata: {userdata}
                Reason code: {reason_code}
                Properties: {properties}''')
        self.mqtt_client.publish(f"{self.BASE_TOPIC}/status", "online", qos=2, retain=True)

    def _on_connect_fail(self, client: mqtt.Client, userdata):
        log.error(f"Connection to MQTT broker failed.")

    def _on_disconnect(self, client: mqtt.Client, userdata, disconnect_flags, reason_code, properties):
        log.warning(f'''Disconnected from MQTT broker. Details:
                Flags: {disconnect_flags}
                Userdata: {userdata}
                Reason code: {reason_code}
                Properties: {properties}''')
        self.ha_republish = True
        
    def _on_subscribe(self, client: mqtt.Client, userdata, mid, reason_code_list, properties):
        log.debug(f"Topic subscription successful.")

    def _on_message(self, client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
        log.debug(f"Received message:\n{message.topic}  :  {message.payload.decode('utf-8')}")

        if self.ha_registered:
            if message.topic == self.ha_status_topic:
                if message.payload.decode("utf-8") == "offline":
                    log.warning(f"Home Assistant MQTT status is OFFLINE.")
                elif message.payload.decode("utf-8") == "online":
                    log.info(f"Home Assistant MQTT status is ONLINE.")
                    self.ha_republish = True
            