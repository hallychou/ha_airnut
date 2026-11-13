"""Airnut 1S integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import CONF_IP, DOMAIN, PLATFORMS
from .socket_server import AirnutAsyncSocketServer

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Airnut 1S integration from YAML."""
    if DOMAIN in config:
        domain_data = hass.data.setdefault(DOMAIN, {})
        if "server" not in domain_data:
            server = AirnutAsyncSocketServer(hass, config[DOMAIN])
            await server.start()
            domain_data["server"] = server
        else:
            _LOGGER.info("Socket server already initialized from YAML, skip")

        for sensor_config in config.get("sensor", []):
            if sensor_config.get("platform") == DOMAIN:
                hass.async_create_task(
                    hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": "import"},
                        data=sensor_config,
                    )
                )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Airnut 1S from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    server = domain_data.get("server")
    if server is None:
        server = AirnutAsyncSocketServer(hass, entry.data)
        await server.start()
        domain_data["server"] = server

    server.register_device(entry.data[CONF_IP], {**entry.data, **entry.options})
    setup_complete = False
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        setup_complete = True
    finally:
        if not setup_complete:
            server.unregister_device(entry.data[CONF_IP])
            if not server.has_registered_devices:
                await server.stop()
                domain_data.pop("server", None)
                if not domain_data:
                    hass.data.pop(DOMAIN, None)
    entry.async_on_unload(entry.add_update_listener(async_update_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and stop the server when its last device is removed."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    domain_data = hass.data.get(DOMAIN, {})
    server: AirnutAsyncSocketServer | None = domain_data.get("server")
    if server is not None:
        server.unregister_device(entry.data[CONF_IP])
        if not server.has_registered_devices:
            await server.stop()
            hass.data.pop(DOMAIN, None)
            _LOGGER.info("All Airnut entries unloaded, server stopped")

    return True


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
