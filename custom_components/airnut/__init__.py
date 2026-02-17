"""Airnut 1S integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import CONF_SCAN_INTERVAL, DOMAIN, PLATFORMS, DEFAULT_SCAN_INTERVAL, DEFAULT_NIGHT_START, DEFAULT_NIGHT_END, DEFAULT_NIGHT_UPDATE
from .socket_server import AirnutAsyncSocketServer

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Airnut 1S integration from YAML."""
    # 即使没有YAML配置，也初始化基础数据（避免KeyError）
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if DOMAIN in config:
        # 从YAML加载配置并启动Socket服务（单例模式，避免重复）
        if "server" not in hass.data[DOMAIN]:
            server = AirnutAsyncSocketServer(hass, config[DOMAIN])
            await server.start()
            hass.data[DOMAIN]["server"] = server
        else:
            _LOGGER.info("Socket server already initialized from YAML, skip")

        # 导入YAML configs as config entries
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
    # 关键修复：如果hass.data[DOMAIN]未初始化，先创建
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    # 如果Socket服务未启动，使用默认配置初始化（单例模式）
    if "server" not in hass.data[DOMAIN]:
        default_config = {
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            "night_start": DEFAULT_NIGHT_START,
            "night_end": DEFAULT_NIGHT_END,
            "night_update": DEFAULT_NIGHT_UPDATE
        }
        server = AirnutAsyncSocketServer(hass, default_config)
        await server.start()
        hass.data[DOMAIN]["server"] = server
        _LOGGER.info("Airnut Socket server initialized with default config (UI mode)")
    else:
        _LOGGER.info("Socket server already exists, skip reinitialization")

    # 加载Sensor平台
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_entry))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry (确保停止服务时彻底释放端口)"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    # Stop server only if no more entries
    if not hass.config_entries.async_entries(DOMAIN):
        if "server" in hass.data.get(DOMAIN, {}):
            server: AirnutAsyncSocketServer = hass.data[DOMAIN]["server"]
            await server.stop()  # 调用完善后的stop方法
            AirnutAsyncSocketServer._instance = None  # 重置单例
        hass.data.pop(DOMAIN, None)
        _LOGGER.info("All Airnut entries unloaded, server stopped")
    return unload_ok

async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update config entry."""
    await hass.config_entries.async_reload(entry.entry_id)