"""Config flow for Airnut 1S integration."""
import logging
import uuid
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_IP,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_NIGHT_UPDATE,
    CONF_SCAN_INTERVAL,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_NIGHT_UPDATE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class AirnutConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Airnut 1S (批量创建多传感器)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step (仅填写设备IP和全局配置)."""
        errors = {}

        if user_input is not None:
            # 验证IP格式
            if not self._validate_ip(user_input[CONF_IP]):
                errors[CONF_IP] = "invalid_ip"
            else:
                # 用设备IP作为唯一ID（确保一个IP只创建一个配置条目）
                unique_id = f"airnut_{user_input[CONF_IP]}_{uuid.uuid4().hex[:8]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates=user_input)
                
                # 配置条目标题（仅显示设备IP）
                title = f"Airnut 1S ({user_input[CONF_IP]})"
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                )

        # 简化schema：移除传感器类型选择
        data_schema = vol.Schema(
            {
                vol.Required(CONF_IP): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=30)
                ),
                vol.Optional(CONF_NIGHT_START, default=DEFAULT_NIGHT_START): str,
                vol.Optional(CONF_NIGHT_END, default=DEFAULT_NIGHT_END): str,
                vol.Optional(CONF_NIGHT_UPDATE, default=DEFAULT_NIGHT_UPDATE): bool,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    def _validate_ip(ip: str) -> bool:
        """Simple IP validation (IPv4 only)."""
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        for part in parts:
            if not part.isdigit() or not 0 <= int(part) <= 255:
                return False
        return True

    async def async_step_import(self, import_config: dict) -> FlowResult:
        """Handle import from YAML config."""
        return await self.async_step_user(import_config)