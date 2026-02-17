"""Sensor platform for Airnut 1S integration (使用device_class默认图标)."""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_IP, DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)

# 生成传感器描述符（仅保留device_class和单位，移除icon）
SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=key,
        name=SENSOR_TYPES[key]["name"],
        device_class=SENSOR_TYPES[key]["device_class"],
        native_unit_of_measurement=SENSOR_TYPES[key]["native_unit_of_measurement"]
        # 移除icon参数，让HA自动分配
    )
    for key in SENSOR_TYPES.keys()
]

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Airnut 1S sensors (批量创建，使用默认图标)."""
    if DOMAIN not in hass.data or "server" not in hass.data[DOMAIN]:
        _LOGGER.error("Airnut server not initialized")
        return
    
    server = hass.data[DOMAIN]["server"]
    device_ip = entry.data[CONF_IP]
    
    entities = []
    for description in SENSOR_DESCRIPTIONS:
        entities.append(AirnutSensor(entry, server, device_ip, description))
    
    async_add_entities(entities, update_before_add=True)

class AirnutSensor(SensorEntity):
    """Airnut 1S Sensor Entity (使用HA原生默认图标)."""
    _attr_should_poll = True
    _attr_available = True

    def __init__(
        self,
        entry: ConfigEntry,
        server,
        device_ip: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize sensor (仅保留核心属性，无手动icon)."""
        self._entry = entry
        self._server = server
        self._device_ip = device_ip
        self.entity_description = description
        
        self._attr_unique_id = f"airnut_{device_ip}_{description.key}_standard"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"airnut_{device_ip}_standard")},
            name=f"Airnut 1S ({device_ip})",
            manufacturer="Airnut",
            model="1S",
        )
        self._attr_name = f"Airnut 1S {description.name}"
        self._attr_native_value = 0

    async def async_update(self):
        """Update sensor state (逻辑不变)."""
        await self._server.update_device_data()
        device_data = self._server.get_device_data(self._device_ip)
        
        if not device_data:
            _LOGGER.debug(f"No data for device {self._device_ip}")
            return
        
        if self.entity_description.key == "temperature":
            self._attr_native_value = device_data.temperature or 0
        elif self.entity_description.key == "humidity":
            self._attr_native_value = device_data.humidity or 0
        elif self.entity_description.key == "pm25":
            self._attr_native_value = device_data.pm25 or 0
        elif self.entity_description.key == "co2":
            self._attr_native_value = device_data.co2 or 0
        
        _LOGGER.debug(f"Updated {self.name} to {self._attr_native_value} {self.entity_description.native_unit_of_measurement}")