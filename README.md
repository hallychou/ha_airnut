# Airnut 1S - Home Assistant Integration

[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.8%2B-blue)](https://www.home-assistant.io/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

[中文](README_zh.md) | [English](README.md)

Home Assistant integration for the Airnut 1S (空气果1S). It automatically retrieves temperature, humidity, PM2.5 and CO₂ data, runs fully locally, and depends on no third-party server.

## Features
✅ Asynchronous socket service architecture: socket communication built on HA's async IO model, never blocking HA's main thread, for better performance  
✅ Standardized config flow: a visual configuration wizard that supports customizing the device IP, scan interval and night-time update strategy  
✅ One-shot bulk entity creation: configuring a single device IP generates the temperature/humidity/PM2.5/CO₂ sensor entities automatically, no need to add them one by one  
✅ Follows native HA conventions: strictly conforms to `SensorEntity`, with native device classes, units of measurement and icons matched automatically — no manual configuration needed  
✅ Local-only data flow: DNS hijacking routes the device's data straight into HA, so all traffic stays on the internal network and never traverses the public internet, improving privacy  
✅ Flexible update strategy: configurable scan interval plus a toggleable night-time update switch, balancing data freshness against device power use  
✅ Connection and polling management: honors each device's scan interval and night policy, clears caches when disconnecting, and correctly releases port 10511  
✅ High-version compatibility: works with Home Assistant 2024.8+, across HA OS / Supervised / Docker / manual installs

## Prerequisites
### 1. Network requirements
- The Airnut 1S device and Home Assistant are on the same LAN
- Your router supports DNS hijacking (used to redirect the Airnut 1S cloud requests to HA)

### 2. DNS hijacking configuration
Configure DNS hijacking on your router so that `apn.airnut.com` resolves to Home Assistant's LAN IP (e.g. `192.168.31.100`):
- Most routers (OpenWRT / Merlin / Asus, etc.) offer this under "custom DNS resolution" or "local domain" settings
- If your router doesn't support it, use AdGuard Home or Pi-hole to perform the DNS hijacking

### 3. Airnut 1S device configuration
- Make sure the Airnut 1S has completed its Wi-Fi setup and is connected to the same network as HA
- The device indicator light is green (normal operating state)

## Installation
### Method 1: HACS
This repository can be installed as a custom HACS repository. It is not yet included in the HACS default store.
1. In HACS, open the integration page and select the three-dot menu → **Custom repositories**
2. Add `hallychou/ha_airnut` with the category **Integration**
3. Find **Airnut 1S**, download it, and restart Home Assistant

Once the repository is included in the HACS default store, adding it as a custom repository will no longer be necessary.

### Method 2: Manual install
1. Copy `custom_components/airnut` into the `custom_components` folder in Home Assistant's `config` directory
2. Restart Home Assistant core

## Configuration steps
1. After restarting HA, go to "Settings → Devices & Services → Add integration"
2. Search for "Airnut 1S" and select it
3. Choose automatic discovery or fill in the configuration manually:
   - **Discover devices**: when enabled, the wizard listens for a device connection for up to 30 seconds and uses the device IP automatically. Make sure `apn.airnut.com` already resolves to HA; if no device is connected, restart the device and retry.
   - **Device IP**: enter the Airnut 1S LAN IP manually (e.g. `192.168.31.113`)
   - **Scan interval** (optional): data refresh interval (default 600 seconds, minimum 30 seconds)
   - **Night period** (optional): night start/end times (default 23:00 - 06:00)
   - **Night update** (optional): whether to keep updating data during the night (default enabled)
4. After submitting, HA automatically creates the 4 sensor entities and groups them under an `Airnut 1S (device IP)` device entry

## Sensor entities
| Entity name | Device class (`device_class`) | Unit | Description |
|-------------|-----------------------|------|----------------|
| Airnut 1S Temperature | temperature | °C | Temperature sensor |
| Airnut 1S Humidity | humidity | % | Humidity sensor |
| Airnut 1S PM2.5 | pm25 | µg/m³ | PM2.5 sensor |
| Airnut 1S CO2 | co2 | ppm | CO₂ sensor |

## Configuration parameters
| Parameter name | Type | Default | Description |
|----------------|------|---------|-------------|
| ip | string | - | Airnut 1S LAN IP (required) |
| scan_interval | integer | 600 | Data scan interval (seconds) |
| night_start | string | 23:00 | Night period start time (HH:MM) |
| night_end | string | 06:00 | Night period end time (HH:MM) |
| night_update | boolean | True | Whether to update data during the night |

## Troubleshooting
### Q1: "already_configured" when adding the integration
- Cause: a stale config entry left in HA's background storage
- Fix:
  1. Enable HA advanced mode, go to "Developer Tools → Actions"
  2. Call the `config_entries.async_remove` action to delete the Airnut-related `entry_id`
  3. Or edit `config/.storage/core.config_entries` directly and remove the related entry

### Q2: Sensor entities appear but show no data
- Check that DNS hijacking is in effect: run `nslookup apn.airnut.com` in the HA terminal and confirm it returns HA's LAN IP
- Check whether the socket service port (10511) is occupied: `netstat -tulpn | grep 10511`
- Restart the Airnut 1S device so it reconnects to Wi-Fi and re-resolves DNS

### Q3: Port in use error (Errno 98)
- Cause: port 10511 is held by another process
- Fix:
  1. Find the offending process: `ss -tulpn | grep 10511`
  2. Kill it: `kill -9 PID`
  3. Restart HA — it recovers automatically

## Data flow
1. The Airnut 1S sends its data-report requests to `apn.airnut.com` (hijacked by DNS into HA)
2. HA's built-in async socket service receives and parses the packet containing the full dataset
3. The server stores temperature, humidity, PM2.5 and CO₂ data in one place
4. All four sensors sync from that same source, guaranteeing data consistency

## Standalone communication test
`airnut_test_server.py` in the repository root is a standalone test server using only the Python standard library — it does not depend on Home Assistant. It listens for device connections, prints login and sensor reports, and replies per the integration protocol: answer login, request sensor data, and once the first dataset arrives set the device volume to 0.

```bash
python airnut_test_server.py
```

It listens on `0.0.0.0:10511` by default. The machine running the script must be on the same LAN as the Airnut 1S, with `apn.airnut.com` resolved/hijacked to that machine's LAN IP. The device uses port 10511; make sure nothing else — the Home Assistant integration or another program — holds it. Use `--host` and `--port` to change the listen address and port (the port must match the one the device connects to). Press `Ctrl+C` to stop.

The server uses the last five digits of the login message's `param.imei` as the `socket_id`, preserving leading zeros (e.g. `MJBM16081700259` becomes `00259`).

## Compatibility
- Home Assistant version: 2024.8+
- Airnut device model: Airnut 1S
- Runtime environments: HA OS / Supervised / Docker / manual install

## License
This project is open source under the MIT license.

## Disclaimer
- This integration is intended for personal, non-commercial use only
- The author accepts no responsibility for device damage, data loss or similar issues
- Ensure your usage complies with applicable laws and regulations before use
