"""Config flow for Airnut 1S integration."""
import ipaddress
from datetime import datetime

import voluptuous as vol

from homeassistant import config_entries
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

class AirnutConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Airnut 1S (批量创建多传感器)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step (仅填写设备IP和全局配置)."""
        errors = {}

        if user_input is not None:
            user_input.setdefault(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            user_input.setdefault(CONF_NIGHT_START, DEFAULT_NIGHT_START)
            user_input.setdefault(CONF_NIGHT_END, DEFAULT_NIGHT_END)
            user_input.setdefault(CONF_NIGHT_UPDATE, DEFAULT_NIGHT_UPDATE)
            ip = user_input[CONF_IP].strip()
            if not self._validate_ip(ip):
                errors[CONF_IP] = "invalid_ip"
            elif not all(
                self._validate_time(user_input[key])
                for key in (CONF_NIGHT_START, CONF_NIGHT_END)
            ):
                if not self._validate_time(user_input[CONF_NIGHT_START]):
                    errors[CONF_NIGHT_START] = "invalid_time"
                if not self._validate_time(user_input[CONF_NIGHT_END]):
                    errors[CONF_NIGHT_END] = "invalid_time"
            else:
                ip = str(ipaddress.IPv4Address(ip))
                user_input[CONF_IP] = ip
                if any(
                    entry.data.get(CONF_IP) == ip
                    for entry in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")

                await self.async_set_unique_id(f"airnut_{ip}")
                self._abort_if_unique_id_configured(updates=user_input)

                title = f"Airnut 1S ({ip})"
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
        try:
            ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError:
            return False
        return True

    @staticmethod
    def _validate_time(value: str) -> bool:
        """Validate a 24-hour HH:MM value."""
        try:
            parsed = datetime.strptime(value, "%H:%M")
        except (TypeError, ValueError):
            return False
        return value == parsed.strftime("%H:%M")

    async def async_step_import(self, import_config: dict) -> FlowResult:
        """Handle import from YAML config."""
        return await self.async_step_user(import_config)
