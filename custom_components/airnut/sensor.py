"""Airnut 1S 传感器平台（已修复夜间更新策略）"""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
    CONF_IP,
    CONF_SCAN_INTERVAL,
    CONF_NIGHT_START,
    CONF_NIGHT_END,
    CONF_NIGHT_UPDATE,
    DOMAIN,
    SENSOR_TYPES
)

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=key,
        name=SENSOR_TYPES[key]["name"],
        device_class=SENSOR_TYPES[key]["device_class"],
        native_unit_of_measurement=SENSOR_TYPES[key]["native_unit_of_measurement"],
        state_class=SENSOR_TYPES[key]["state_class"],
    )
    for key in SENSOR_TYPES.keys()
]

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if DOMAIN not in hass.data or "server" not in hass.data[DOMAIN]:
        _LOGGER.error("Airnut server 未初始化")
        return

    server = hass.data[DOMAIN]["server"]
    device_ip = entry.data[CONF_IP]

    entities = [
        AirnutSensor(hass, entry, server, device_ip, desc)
        for desc in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities, update_before_add=True)


class AirnutSensor(SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        server,
        device_ip: str,
        description: SensorEntityDescription,
    ):
        self.hass = hass
        self._entry = entry
        self._server = server
        self._device_ip = device_ip
        self.entity_description = description

        self._attr_unique_id = f"airnut_{device_ip}_{description.key}"
        self._attr_should_poll = True
        self._attr_available = True
        self._attr_native_value = None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"airnut_{device_ip}" )},
            name=f"Airnut 1S ({device_ip})",
            manufacturer="Airnut",
            model="1S",
        )

        # 读取夜间配置
        self._night_update = entry.options.get(CONF_NIGHT_UPDATE, entry.data.get(CONF_NIGHT_UPDATE, True))
        self._night_start = entry.options.get(CONF_NIGHT_START, entry.data.get(CONF_NIGHT_START, "23:00"))
        self._night_end = entry.options.get(CONF_NIGHT_END, entry.data.get(CONF_NIGHT_END, "06:00"))

    @property
    def _is_night_time(self):
        """判断当前是否在夜间时段"""
        now = dt_util.now().time()
        try:
            night_start = datetime.strptime(self._night_start, "%H:%M").time()
            night_end = datetime.strptime(self._night_end, "%H:%M").time()
        except:
            return False

        if night_start <= night_end:
            return night_start <= now <= night_end
        else:
            return now >= night_start or now <= night_end

    async def async_update(self):
        # ====================== 夜间策略核心 ======================
        if not self._night_update and self._is_night_time:
            _LOGGER.debug("夜间模式：跳过更新 %s", self.name)
            return
        # ==========================================================

        await self._server.update_device_data()
        data = self._server.get_device_data(self._device_ip)
        if not data:
            return

        key = self.entity_description.key
        if key == "temperature":
            self._attr_native_value = data.temperature
        elif key == "humidity":
            self._attr_native_value = data.humidity
        elif key == "pm25":
            self._attr_native_value = data.pm25
        elif key == "co2":
            self._attr_native_value = data.co2