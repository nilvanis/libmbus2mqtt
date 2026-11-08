# Home Assistant Integration

When `homeassistant.enabled` is set to `true`, libmbus2mqtt automatically creates devices and entities in Home Assistant using MQTT Discovery.

## Bridge Device

libmbus2mqtt creates a "Bridge" device in Home Assistant with these entities:

| Entity               | Type   | Description                                          |
| -------------------- | ------ | ---------------------------------------------------- |
| Discovered Devices | Sensor | Number of M-Bus devices found |
| Online Devices | Sensor | Number of devices currently responding |
| Firmware Version | Sensor | libmbus2mqtt version |
| Last Scan | Sensor | When devices were last scanned (disabled by default) |
| Uptime | Sensor | How long the bridge has been running (disabled by default) |
| Last Poll Duration | Sensor | Duration of last polling cycle in ms (disabled by default) |
| Rescan Devices | Button | Trigger a new device scan |
| Log Level | Select | Change logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| Poll Interval | Number | Change polling interval (10-3600 seconds) |

>[!IMPORTANT]
> Settings changed via MQTT (e.g. `Log level`) are changed only for the current **runtime**, meaning it will revert to config.yaml setting (or default if not set) after restart of libmbus2mqtt.

## M-Bus Devices

Each discovered M-Bus meter appears as a separate device in Home Assistant, linked to the Bridge device. The entities created depend on:

1. **Device template** - If a template exists for your meter, entities are created with proper names, units, and icons (see [Device Templates](templates.md))
2. **Generic fallback** - If no template exists, generic sensors are created for each data record

If a different physical device appears later on the same M-Bus address, libmbus2mqtt marks the previous device as unavailable, renames it with ` (replaced)`, and activates the new device. If the original device comes back on that address later, the same identity is reused.

If the same device starts returning a different number of `<DataRecord>` items, libmbus2mqtt rematches the template for that same device. Entities that are no longer present become unavailable and are reactivated if they return later.

The MQTT topics used by these entities are listed in [MQTT](mqtt.md#mqtt-topics).
