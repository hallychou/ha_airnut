"""Airnut 1S sensor platform."""
import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_IP, DOMAIN, SENSOR_TYPES
from .socket_server import AirnutAsyncSocketServer

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=key,
        name=sensor_type["name"],
        device_class=sensor_type["device_class"],
        native_unit_of_measurement=sensor_type["native_unit_of_measurement"],
        state_class=sensor_type["state_class"],
    )
    for key, sensor_type in SENSOR_TYPES.items()
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for an Airnut device."""
    server: AirnutAsyncSocketServer | None = hass.data.get(DOMAIN, {}).get("server")
    if server is None:
        _LOGGER.error("Airnut server is not initialized")
        return

    device_ip = entry.data[CONF_IP]
    async_add_entities(
        [
            AirnutSensor(server, device_ip, description)
            for description in SENSOR_DESCRIPTIONS
        ],
        update_before_add=True,
    )


class AirnutSensor(SensorEntity):
    """Representation of one Airnut 1S measurement."""

    def __init__(
        self,
        server: AirnutAsyncSocketServer,
        device_ip: str,
        description: SensorEntityDescription,
    ) -> None:
        self._server = server
        self._device_ip = device_ip
        self.entity_description = description
        self._attr_unique_id = f"airnut_{device_ip}_{description.key}"
        self._attr_should_poll = True
        self._attr_available = False
        self._attr_native_value = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"airnut_{device_ip}")},
            name=f"Airnut 1S ({device_ip})",
            manufacturer="Airnut",
            model="1S",
        )

    async def async_update(self) -> None:
        """Request the latest device data and update this sensor."""
        await self._server.update_device_data(self._device_ip)
        data = self._server.get_device_data(self._device_ip)
        if data is None:
            self._attr_available = False
            return

        self._attr_available = True
        self._attr_native_value = getattr(data, self.entity_description.key)
