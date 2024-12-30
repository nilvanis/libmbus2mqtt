import xml.etree.ElementTree as ET
import subprocess
import logging.config
import json
import re
import os

from pathlib import Path
from datetime import datetime


if __name__ == '__main__':
    from pprint import pprint

log = logging.getLogger(__name__)

regex_deviceid = re.compile(r'^(?!0)(250|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
regex_baudrate = re.compile(r'^\d+$')
regex_scan_device_found = re.compile(r'Found a M-Bus device at address (25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)')

main_filepath = Path(__file__).resolve().parent

class MbusDeviceID:
    '''Descriptor for M-Bus Device ID'''

    def __get__(self, obj, type=None) -> object:
        return obj._device_id
    
    def __set__(self, obj, value):
        if type(value) == int:
            value = str(value)
        if not re.match(regex_deviceid, value):
            raise ValueError("'device_id' must be between 1-254")
        else:
            obj._device_id = value

class DeviceAvailability:
    '''
    Availability parameters.
    To be used with Device class, primarily for Home Assistant availability status updates.
    '''
    def __init__(self):
        self._init = True
        self._status = None
        self.FAILS_TO_DECLARE_OFFLINE = 3  # HARDCODED

        self.update = None

        self.last_poll_status = None
        self.last_poll_datetime = None
        self.poll_fail_count = 0
        self.poll_consecutive_fails = 0

    @property
    def status(self):
        return self._status
    
    @status.setter
    def status(self, value):
        allowed_options = ["online", "offline"]
        if self._init:
            allowed_options.append(None)
        if value not in allowed_options:
            raise ValueError("Staus can be either 'online' or 'offline'")
        if value != self._status:
            self.update = True
        self._status = value

        self._init = False

    def poll_fail(self):
        self.status = "offline"
        self.last_poll_status = "fail"
        self.last_poll_datetime = datetime.now()
        self.poll_fail_count += 1
        self.poll_consecutive_fails += 1

        if self.poll_consecutive_fails >= self.FAILS_TO_DECLARE_OFFLINE:
            self.status = "offline"

    def poll_success(self):
        self.status = "online"
        self.last_poll_status = "success"
        self.last_poll_datetime = datetime.now()
        self.poll_consecutive_fail = 0

    def get_data(self) -> dict:
        return self.__dict__


class Interface:
    '''
    Class definition for a libmbus interface

    libmbus_path:   Path to a directory, where all libmbus binaries are located
    baudrate:       baudrate at which the Mbus device is configured
    serial_device:  tty path, where serial Mbus converter is available
    '''
    device_id = MbusDeviceID()

    def __init__(self, *, libmbus_path, baudrate, serial_device):
        req_mbus_binaries = [
            'mbus-serial-request-data',
            'mbus-serial-scan',
        ]
        libmbus_path_contents = [element for element in Path(libmbus_path).iterdir()]
        for req_binary in req_mbus_binaries:
            if Path(libmbus_path).joinpath(req_binary) not in libmbus_path_contents:
                raise FileNotFoundError(f"libmbus serial binaries not found in {libmbus_path}")
            
        try: baudrate = str(baudrate)
        except: raise ValueError(f"Invalid baudrate: {baudrate}")
        
        if not re.match(regex_baudrate, baudrate):
            raise ValueError(f"Invalid baudrate: {baudrate}")

        if not os.access(serial_device, os.R_OK):
            raise PermissionError(f"Cannot access {serial_device}")

        self.libmbus_path = libmbus_path
        self.baudrate = baudrate
        self.serial_device = serial_device

        self.CONFIG_OK = True

    def scan(self) -> list:
        '''Bus scan method using libmbus in the OS'''

        if not self.CONFIG_OK:
            log.error(f"Cannot scan bus: Interface config invalid.")
            return
        
        log.info(f"Scanning for M-Bus devices via {self.serial_device}, baudrate: {self.baudrate}")
        discovery_output = subprocess.run(
            [
                Path(self.libmbus_path).joinpath('mbus-serial-scan'),
                '-b', self.baudrate,
                self.serial_device
            ],
            capture_output=True
        )
        discovered_devices = re.findall(regex_scan_device_found, discovery_output.stdout.decode("utf-8"))
        for device_id in discovered_devices:
            log.info(f"Found an M-Bus device at address: {device_id}")

        log.info(f"Found {len(discovered_devices)} devices in total.")
        return discovered_devices
    
    def poll(self, device_id) -> ET:
        '''Poller method using libmbus in the OS'''

        if not self.CONFIG_OK:
            log.error(f"Cannot poll device: Interface config invalid.")
            return
 
        self.device_id = device_id
        log.debug(f"Polling M-Bus device {device_id}")
        poll_output = subprocess.run(
            [
                Path(self.libmbus_path).joinpath('mbus-serial-request-data'),
                '-b', self.baudrate,
                self.serial_device,
                device_id
                ],
                capture_output=True
                    )
        
        return ET.fromstring(poll_output.stdout)

class Device:
    '''Class definition for Mbus device accessible via Mbus Interface object'''
    device_id = MbusDeviceID()

    def __init__(self, device_id, /, *, interface: Interface):
        self.device_id = device_id
        self.interface = interface

        # To be populated after successful poll and xml2dict conversion
        self.mbus_data = None
        self.identifier = None
        self.manufacturer = None
        self.model = None
        self.model_id = None
        self.sw_version = None
        self.serial_number = None

        self.homeassistant_template = None
        self.homeassistant_data = None
        self.disabled = False
        self.availability = DeviceAvailability()

        self.homeassistant_discovery_published = False # To track if Home Assistant MQTT Discovery payload was published

    def xml2dict(self, xml_file, /) -> dict:
        '''Convert ElementTree data to dictionary'''
        if type(xml_file) == ET.ElementTree:
            xml_root = xml_file.getroot()
        elif type(xml_file) == ET.Element:
            xml_root = xml_file
        else:
            raise ValueError(f"xml2dict: provided data is not an Element/ElementTree object!")

        def get_childs(element):
            xml_dict = {}
            if len([x for x in element.iter()]) > 1:
                for child in element:
                    if child.tag == 'DataRecord':
                        if 'DataRecord' not in xml_dict:
                            xml_dict['DataRecord'] = {}
                        xml_dict['DataRecord'][child.attrib['id']] = get_childs(child)
                    else:
                        if child.tag == 'SlaveInformation':
                            xml_dict[child.tag] = get_childs(child)
                        else:
                            xml_dict[child.tag] = child.text
            else:
                xml_dict[element.tag] = element.text
            return xml_dict
            
        return get_childs(xml_root)
    
    def poll(self) -> ET:
        try:
            xml_data =  self.interface.poll(self.device_id)
        except ET.ParseError:
            log.error(f"Device ID '{self.device_id}' is unavailabile or does not provide valid data.")
            self.availability.poll_fail()
            return None
        
        self.availability.poll_success()
        return xml_data

    def data_update(self) -> dict:
        try:
            self.mbus_data = self.xml2dict(self.poll())

            self.identifier     = self.mbus_data['SlaveInformation']['Id']
            self.manufacturer   = self.mbus_data['SlaveInformation']['Manufacturer']
            if not self.mbus_data['SlaveInformation']['ProductName']:
                self.model      = "M-Bus Device"
            else:
                self.model      = self.mbus_data['SlaveInformation']['ProductName']
            self.model_id       = self.mbus_data['SlaveInformation']['Medium']
            self.sw_version     = self.mbus_data['SlaveInformation']['Version']
            self.serial_number  = self.mbus_data['SlaveInformation']['Id']
            if not self.mbus_data['SlaveInformation']['ProductName']:
                self.name       = f"M-Bus Device ({self.serial_number})"
            else:
                self.name       = f"{self.mbus_data['SlaveInformation']['ProductName']} ({self.serial_number})"
        except Exception as e:
            log.exception(e)
            return None
        return self.mbus_data
    
    def homeassistant_get_template(self) -> json:
        HA_RELATIVE_TEMPLATE_PATH = 'data/homeassistant_mappings'
        TEMPLATES_INDEX_FILENAME = 'index.json'

        ha_template_path = main_filepath.joinpath(HA_RELATIVE_TEMPLATE_PATH)
        # Match components template based on 'index.json'
        ha_template_index_filepath = Path(ha_template_path).resolve().joinpath(TEMPLATES_INDEX_FILENAME)
        ha_templates = [dirpath.resolve() for dirpath in Path(ha_template_path).iterdir() if dirpath.parts[-1] != TEMPLATES_INDEX_FILENAME]
        with open(ha_template_index_filepath) as file:
            ha_template_index = json.load(file)
        
        for filename, matchlist in ha_template_index.items():
            for match in matchlist:
                if matchlist[match] == self.mbus_data['SlaveInformation'][match]:
                    device_template_filename = filename
                else:
                    device_template_filename = None
                    break
            if device_template_filename:
                break
        if device_template_filename:
            # Get template file path and load the file
            for filepath in ha_templates:
                if filepath.parts[-1] == device_template_filename:
                    device_template_filepath = filepath
            
            with open(device_template_filepath) as file:
                self.homeassistant_template = json.load(file)
        else:
            raise ValueError(f"Could not match any template file for:\n{pprint(self.mbus_data['SlaveInformation'])}")

        # Generate unique_id for each component
        for component_id in self.homeassistant_template:
            json_name = self.homeassistant_get_template_component_json_value(component_id)
            uid = f"{self.serial_number}_{json_name}"
            self.homeassistant_template[component_id]['unique_id'] = re.sub(r'[^a-zA-Z0-9_]', '', uid)

        return self.homeassistant_template
    
    def homeassistant_get_data(self) -> json:
        if not self.homeassistant_template:
            self.homeassistant_get_template()
        if not self.mbus_data:
            self.data_update()
        homeassistant_data = {}
        for component_id in self.homeassistant_template:
            json_name = self.homeassistant_get_template_component_json_value(component_id)
            homeassistant_data[json_name] = self.mbus_data['DataRecord'][component_id]['Value']
        self.homeassistant_data = json.dumps(homeassistant_data)

        return self.homeassistant_data
    
    def homeassistant_get_template_component_json_value(self, component_id):
            '''Get component json field name for state payload'''
            regex = re.compile(r"(?<=value_json\.)(\S+)")
            value_template = self.homeassistant_template[component_id]['value_template']
            json_value_name = re.search(regex, value_template).group()

            return json_value_name
