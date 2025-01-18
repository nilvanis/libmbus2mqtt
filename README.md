# libmbus2mqtt
**Disclaimer**: This tool was mainly written to suffice my needs, which are: reading my two wired M-Bus water meters and send it to Home Assistant.
I know there are many things which can be improved, but it's working good enough for me and someone else can try to use it as well.

Software is published 'as-is' without any guarantees.

## Features
- Reading M-Bus devices via 'TTL to M-Bus' converter
- Automatic discovery of connected M-Bus meters
- Publishing data to MQTT
- Optional Home Assistant MQTT Discovery compliance:
    - automatic device and entity creation and update
    - device unavailability reporting
- Template system to support different M-Bus devices

## Requirements
- TTL to M-Bus Master, like [this one](https://www.aliexpress.com/item/1005003292386193.html)
- Raspberry Pi or anything with UART (USB-TTL converter should work as well, but have not tested)
- Linux (tested on Raspbian 12)
- [libmbus](https://github.com/rscada/libmbus)
- python3 (tested on version 3.11)

## Installation
1. Clone this git repo and enter the directory:
    ```cli
    git clone https://github.com/nilvanis/libmbus2mqtt
    cd libmbus2mqtt
    ```

2. Create virtual environment and activate it:
    ```cli
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. Install required libraries:
    ```cli
    python3 -m pip install -r requirements.txt
    ```

4. Install libmbus\
(you can check [here](https://bends.se/?page=anteckningar/automation/m-bus/libmbus) for an example installation method)

5. Prepare config.yaml
    ```cli
    cp template_config.yaml config.yaml
    nano config.yaml
    ```
    Change settings to reflect your setup. More info [here](#configyaml).  
    Save file and exit (Ctrl+O, Ctrl+X).

### (Optional) Prepare and match device template for Home Assistant
In case you use HA MQTT Discovery, check if your meter is on the [supported devices](#supported-devices-home-assistant-mqtt-discovery) list.\
If not, you must prepare a valid device template.

Templates are stored as json files in ```libmbus2mqtt/data/homeassistant_mappings```.\
To match a proper template, libmbus2mqtt uses definitions from ```index.json``` file.\
Each entry syntax in ```index.json``` is as follows:
```json
    "<TEMPLATE_FILENAME.json>": {
        "Manufacturer": "ASDX",
        "ProductName": "Super Water Meter"
    }
```
For matching, you can use any field from ```<SlaveInformation>``` [libmbus xml output](#libmbus-xml-output).

**Device template JSON file** syntax is as follows:
```json
{
    "0": {
        "name": "Fabrication Number",
        "icon": "mdi:numeric",
        "platform": "sensor",
        "value_template":"{{ value_json.fabrication_number }}",
        "entity_category": "diagnostic"
    },
    "1": {
        name, icon, platform, etc...
    },
    "2": {
        name, icon, platform, etc...
    },
    <...>
}
```
```0```, ```1```, etc. are section numbers defined as ```id``` number in ```<DataRecord id>``` from [libmbus xml output](#libmbus-xml-output).\
You must identify which section holds what information and based on that create a template.\
Or you can just have generic sensors for everything.

If you need help, raise an [issue](https://github.com/nilvanis/libmbus2mqtt/issues) and paste there your libmbus xml output, and I'll try to add a new template for you.
  

## Running the tool
To start libmbus2mqtt, simply run:
```cli
python3 main.py
```
First, configuration will be loaded, libmbus path checked and then M-Bus will be scanned for available devices.\
All found devices data will be published to MQTT.
  

### (Optional) Run as systemd service
You can run libmbus2mqtt as a service in the background and instruct the system to load it every time system boots.\
In order to do that, create a new service file:
```cli
sudo nano /etc/systemd/system/libmbus2mqtt.service
```
Paste there:
```cli
[Unit]
Description=libmbus2mqtt
After=multi-user.target
[Service]
Type=simple
Restart=always
ExecStart=/home/user/libmbus2mqtt/.venv/bin/python3 /home/user/libmbus2mqtt/main.py
[Install]
WantedBy=multi-user.target
```
Where ```/home/user/libmbus2mqtt/``` is your actual libmus2mqtt location.
Save the file and exit (Ctrl+O, Ctrl+X).  
Now enable and run the service:
```cli
sudo systemctl enable libmbus2mqtt.service
sudo systemctl start libmbus2mqtt.service
```
  

## Additional Info

### config.yaml
```yaml
poll_interval: 60                   # [in seconds] How often M-Bus devices will be polled

mqtt:
  host: example.com                 # IP address or FQDN of your MQTT server (or Home Assistant if you use 'Mosquitto broker' add-on)
  port: 1883                        # Port of the MQTT broker, by default 1883
  username: user
  password: pass
  base_topic: libmbus2mqtt          # Base topic under which devices info will be published
  #custom_topic: example/devices/   # Setting this overrides base_topic and disables homeassistant section

interface:
  libmbus_path: /usr/local/bin/     # Path where libmbus libraries are available
  baudrate: 2400
  serial_device: /dev/ttyAMA0       # Path where M-Bus Master is available via serial

homeassistant:
  autodiscovery: True               # Enable Home Assistant MQTT Discovery format for data publishing
  discovery_prefix: homeassistant   # Home Assistant MQTT Discovery prefix. By default: homeassistant
```
  
  
### libmbus XML output
To test your libmbus installation, try below commands:
```cli
/usr/local/bin/mbus-serial-scan -b 2400 /dev/ttyAMA0
```
Where ```-b``` is your M-Bus baudrate and ```/dev/ttyAMA0``` is your serial device.
Expected output should be similar to this:
```cli
Found a M-Bus device at address 1
```
Next, poll an M-Bus device:
```cli
/usr/local/bin/mbus-serial-request-data -b 2400 /dev/ttyAMA0 1
```
where ```1``` is the discovered device address.

You should get a response similar to this:
```xml
<MBusData>

    <SlaveInformation>
        <Id>123456789</Id>
        <Manufacturer>ASDX</Manufacturer>
        <Version>1</Version>
        <ProductName>Super Water Meter</ProductName>
        <Medium>Water</Medium>
        <AccessNumber>123</AccessNumber>
        <Status>11</Status>
        <Signature>1111</Signature>
    </SlaveInformation>

    <DataRecord id="0">
        <Function>Instantaneous value</Function>
        <StorageNumber>0</StorageNumber>
        <Unit>Fabrication number</Unit>
        <Value>0987654321</Value>
        <Timestamp>2025-01-05T20:36:14Z</Timestamp>
    </DataRecord>

    <DataRecord id="1">
        <Function>Instantaneous value</Function>
        <StorageNumber>0</StorageNumber>
        <Unit>cust. ID</Unit>
        <Value>          </Value>
        <Timestamp>2025-01-05T20:36:14Z</Timestamp>
    </DataRecord>

    <DataRecord id="2">
        <Function>Instantaneous value</Function>
        <StorageNumber>0</StorageNumber>
        <Unit>Time Point (time &amp; date)</Unit>
        <Value>2025-01-05T22:05:00</Value>
        <Timestamp>2025-01-05T20:36:14Z</Timestamp>
    </DataRecord>

(...and many more <DataRecord> depending on the device)

</MBusData>
```
Based on this output, you can identify each 'sensor' for Home Assistant, where by 'sensor' I mean each DataRecord.\
```<SlaveInformation>``` holds general device information you will also find in the Home Assistant MQTT device section.

  
## How to connect 'TTL to M-BUS' adapter to Raspberry Pi UART
1. First, you need to enable UART. Skip if you already did that.\
    In the Raspberry PI CLI run: 
    ```cli
    sudo raspi-config
    ```
    Next, enable UART by going through the menu:\
    ```3 Interface Options``` -> ```Serial Port``` -> ```<No>``` -> ```<Yes>```

2. Connect adapter to the Raspberry Pi (via 40-PIN GPIO):\
**First make sure all devices are disconnected from any power source!**\
You can verify the Raspberry Pi GPIO pin numbers [here](https://pinout.xyz/)
  
    | Raspberry Pi | TTL to MBUS |
    | -----------  | ----------- |
    | PIN 02 (5V)  | TTLVCC      |
    | PIN 04 (5V)  | VIN         |
    | PIN 06 (GND) | GND         |
    | PIN 08 (TX)  | TXD         |
    | PIN 10 (RX)  | RXD         |
  
    <img src="../assets/libmbus2mqtt_rpi_converter.jpg" width="550">
  
  
3. Power up Raspberry Pi. Serial device should be available at /dev/ttyAMA0
  
  
## Supported devices (Home Assistant MQTT Discovery)

### Itron Cyble M-Bus
![Itron Cyble M-Bus](../assets/itron-cyble-mbus.jpg?raw=true)\
Data sheet: https://se.itron.com/o/commerce-media/accounts/-1/attachments/3809944

### APATOR APT-MBUS-NA-1
![APATOR APT-MBUS-NA-1](../assets/apt-mbus-na-1.jpg?raw=true)\
Data sheet: https://api.apator.com/uploads/oferta/woda-i-cieplo/systemy/przewodowy/apt-mbus-na/apt-mbus-na-1-catalogue.pdf

### Kamstrup Multical 401
<img src="../assets/kamstrup-multical-401.jpg?raw-true" width="600">
Data Sheet: https://documentation.kamstrup.com/docs/MULTICAL_401/en-GB/Data_sheet/CONTF9A902FD213B4A1BB4F5122E640B3AB7/