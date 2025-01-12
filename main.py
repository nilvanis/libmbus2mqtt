import sys
import time
import logging.config
import modules.Libmbus as Libmbus
import modules.ConfigManager as Config
import modules.MQTTHandler as MQTT

from pathlib import Path

VERSION = '1.0'
CONFIG_FILENAME = 'config.yaml'
CONFIG_TEMPLATE_NAME = 'template_config.yaml'

main_filepath = Path(__file__).resolve().parent
config_filepath = main_filepath.joinpath(CONFIG_FILENAME)
cfg = Config.libmbus2mqtt(config_filepath)
if cfg.FLAG_ERROR:
    print(f"Cannot load {CONFIG_FILENAME}! Terminating...")
    sys.exit(1)

# Setup logging
try:
    logfile_relative_filepath = cfg.logger['handlers']['file']['filename']
    cfg.logger['handlers']['file']['filename'] = f"{str(main_filepath)}/{logfile_relative_filepath}" # add absolute path
except:
    pass
logging.config.dictConfig(cfg.logger)
log = logging.getLogger(__name__)
log.debug(f"Logging configured.")

# 'homeassistant' section and its elements are optional
#  If 'custom_topic' is configured, homeassistant config is disabled
if 'custom_topic' in cfg.mqtt:
    CUSTOM_TOPIC = True
    log.info(f"'custom_topic': {cfg.mqtt['custom_topic']} defined in 'config.yaml'.")
else:
    CUSTOM_TOPIC = False

if 'homeassistant' in cfg.__dict__ and CUSTOM_TOPIC:
    log.warning(f"Disabling 'homeassistant' config section. Reason: 'custom_topic' defined.")
    HA_AUTODISCOVERY = False
elif 'homeassistant' in cfg.__dict__:
    try:
        HA_AUTODISCOVERY = cfg.homeassistant['autodiscovery']
    except KeyError:
        HA_AUTODISCOVERY = False
    if HA_AUTODISCOVERY:
        try:
            if cfg.homeassistant['discovery_prefix']:
                HA_DISCOVERY_PREFIX = cfg.homeassistant['discovery_prefix']
            else:
                HA_DISCOVERY_PREFIX = 'homeassistant'
        except KeyError:
            HA_DISCOVERY_PREFIX = 'homeassistant'
    cfg.homeassistant['discovery_prefix'] = HA_DISCOVERY_PREFIX
    log.debug(f"Home Assistant discovery prefix configured to: {HA_DISCOVERY_PREFIX}")
else:
    log.debug(f"'homeassistant' not present in 'config.yaml")
    HA_AUTODISCOVERY = False

log.info(f"Home Assistant MQTT Discovery is: {'ON' if HA_AUTODISCOVERY else 'OFF'}")

try:
    mbus = Libmbus.Interface(**cfg.interface) # Interface init based on config.yaml data
except Exception as e:
    log.exception(e)
    sys.exit(1)
device_id_list = mbus.scan() # Find all devices on connected M-Bus. Ignores errors.

devices = []
for device_id in device_id_list:
    devices.append(Libmbus.Device(device_id, interface=mbus))

mqtt = MQTT.Client(**cfg.mqtt) # MQTT Client config based on config.yaml data
mqtt.connect(HA_AUTODISCOVERY)

# Main loop
while True:
    if mqtt.FLAG_ERROR == True:
        log.critical(f"MQTT Client critical error: Shutting down!")
        sys.exit(1)

    while mqtt.IS_CONNECTED:
        if mqtt.FLAG_ERROR == True:
            log.critical(f"MQTT Client critical error: Shutting down!")
            sys.exit(1)
        for device in devices:
            if device.disabled: continue
            try:
                device_data = device.data_update()
            except Exception as e:
                log.exception(e)
                log.error(f"Could not get proper data from device ID {device.device_id}. Skipping...")
                continue
            if device_data == None:
                log.debug(f"No data received from parsing device ID '{device.device_id}")
                continue

            if HA_AUTODISCOVERY:
                if not mqtt.ha_registered:
                    mqtt.ha_register(cfg.homeassistant)
                    time.sleep(2)
                if mqtt.ha_republish:
                    for dev in devices:
                        dev.homeassistant_discovery_published = False
                    mqtt.ha_republish = False
                if device.homeassistant_discovery_published == False:
                    log.info(f"Publishing Home Assistant MQTT discovery payload for device ID: {device.device_id}")
                    device.homeassistant_get_data()
                    register_msg_info = mqtt.ha_device_register(
                        device,
                        ha_config=cfg.homeassistant,
                        L2M_VERSION=VERSION
                        )
                    if register_msg_info != None:
                        register_msg_info.wait_for_publish(10)
                        if register_msg_info.is_published() == True:
                            device.homeassistant_discovery_published = True
                        else:
                            log.error(f"Publishing Home Assistant MQTT discovery payload for device ID: {device.device_id} FAILED!")
                            log.error(f"MQTT Error Code: {register_msg_info.rc}")
                            log.error(f"Disabling device '{device_id}' poll & publish.")
                            device.disabled = True
                            continue
                    else:
                            log.error(f"Disabling device '{device_id}' poll & publish.")
                            device.disabled = True
                            continue
            log.debug(f"Device availability info: {device.availability.get_data()}")
            log.debug(f"Publishing sensor data for device ID: {device.device_id}")
            mqtt.publish(
                device,
                homeassistant=HA_AUTODISCOVERY
                )
        time.sleep(cfg.poll_interval)

