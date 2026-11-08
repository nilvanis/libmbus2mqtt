# MQTT

## MQTT Topics

Data is published to these MQTT topics (`libmbus2mqtt` is the default `mqtt.base_topic`):

```text
libmbus2mqtt/bridge/state          # Bridge availability (online/offline)
libmbus2mqtt/bridge/info           # Bridge status JSON
libmbus2mqtt/device/{device_id}/state     # Device data JSON
libmbus2mqtt/device/{device_id}/availability  # Device availability
libmbus2mqtt/device/{device_id}/entity/{entity_key}/availability  # Entity availability
libmbus2mqtt/command/rescan        # Trigger rescan (send any message)
libmbus2mqtt/command/log_level     # Change log level (DEBUG/INFO/WARNING/ERROR)
libmbus2mqtt/command/poll_interval # Change poll interval (10-3600)
```

## MQTT over TLS

Set `mqtt.tls.enabled: true` to encrypt the connection. Without an explicit `port`, libmbus2mqtt then connects to `8883`. By default it verifies the broker certificate, which must also list the host name you connect to:

- **Broker certificate from a public CA** (e.g. Let's Encrypt): nothing else to set; the system CAs are used.
- **Private CA or self-signed certificate** (e.g. your own CA for Mosquitto): set `ca_certs` to the CA certificate, or to the broker certificate itself if it's self-signed.
- **Broker requires client certificates** (`require_certificate true` in Mosquitto): also set `certfile` and `keyfile`.
- **No verification**: `insecure: true` accepts any broker certificate, including a self-signed one or one issued for another name (e.g. when connecting by IP), without `ca_certs`. The connection is still encrypted, but anyone who can intercept it could pose as the broker.

```yaml
mqtt:
  host: mqtt.example.lan
  tls:
    enabled: true
    ca_certs: /data/config/certs/ca.crt        # Docker; natively e.g. /etc/libmbus2mqtt/certs/ca.crt
    certfile: /data/config/certs/client.crt
    keyfile: /data/config/certs/client.key
```

In Docker, put the files in `data/config/certs/` on the host. The entrypoint then makes them readable for the container user. Natively, they must be readable by the `libmbus2mqtt` user. libmbus2mqtt checks this at startup.
