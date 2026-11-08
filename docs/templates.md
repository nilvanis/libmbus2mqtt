# Device Templates

Templates define how M-Bus data records are mapped to Home Assistant entities. They provide friendly names, icons, units, and device classes.

## Bundled Templates

libmbus2mqtt includes templates for common devices. Check the [Supported Devices](supported-devices.md) page.

## Custom Templates

You can create custom templates for your devices. Place them in the `templates/` folder of the data directory: `data/templates/` on the host with Docker, `/var/lib/libmbus2mqtt/templates/` natively.

```text
<data directory>/
└── templates/
    ├── index.json              # Maps devices to templates
    └── my_custom_meter.json    # Your template file
```

### index.json

Maps device information to template files:

```json
{
    "my_custom_meter.json": {
        "Manufacturer": "ACME",
        "ProductName": "Water Meter Pro",
        "DataRecordCount": 12
    }
}
```

### Template File

Defines entities for each data record:

```json
{
    "0": {
        "name": "Serial Number",
        "icon": "mdi:identifier",
        "component": "sensor",
        "value_template": "{{ value_json.serial_number }}",
        "entity_category": "diagnostic"
    },
    "1": {
        "name": "Total Volume",
        "icon": "mdi:water",
        "component": "sensor",
        "device_class": "water",
        "state_class": "total_increasing",
        "unit_of_measurement": "m³",
        "value_template": "{{ value_json.volume }}"
    },
    "custom-daily": {
        "name": "Daily Usage",
        "icon": "mdi:water-outline",
        "component": "sensor",
        "unit_of_measurement": "L",
        "value_template": "{{ value_json.daily_usage }}"
    }
}
```

The numbers (`"0"`, `"1"`, etc.) correspond to `<DataRecord id="X">` in the M-Bus XML output. You can also create additional, custom sensors. Every custom sensor JSON section name must be preceded with `custom-`. All section names must be unique.
Since custom sensors don't have their own DataRecord in libmbus XML output, value must be derived from other data.
Common use case is creating dedicated sensors from data in Manufacturer Specific field value.

### Template Lookup Order

- If `template` is set for a device in `config.yaml`, libmbus2mqtt uses that exact template file and skips auto-matching.
- Otherwise, libmbus2mqtt checks `templates/index.json` in the data directory first for user defined index/template.
- If no match or no user-defined index at all, built-in templates are checked.
- Within template index, matches are tried in this order:
  1. `Manufacturer` + `ProductName` + `DataRecordCount`
  2. `Manufacturer` + `ProductName`

> [!NOTE]
> - `DataRecordCount` is the number of `<DataRecord>` items in the libmbus XML return data.
> - Only numbered template entries (`"0"`, `"1"`, ...) count toward `DataRecordCount`, `custom-*` **do not count**.

This lets you add templates without blocking built-in ones; if you want to override a built-in, add a matching entry to your user index and provide the file in the same `templates/` folder.

If the same device later advertises a different `DataRecordCount`, libmbus2mqtt rematches the template for that device instead of creating a new Home Assistant device.

## Getting Your Device's Data Records

To see what data your meter provides, run:

```bash
# Using libmbus2mqtt
libmbus2mqtt scan

# Or directly with libmbus
mbus-serial-request-data -b 2400 /dev/ttyUSB0 1
```

This shows the XML output with all data records. Use this to create a custom template.

Need help? Open an [issue](https://github.com/nilvanis/libmbus2mqtt/issues) with your XML output, and we can help create a template.
