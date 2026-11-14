"""Config flow for Airnut 1S integration."""
import asyncio
import ipaddress
import logging
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
from .socket_server import AirnutAsyncSocketServer

_LOGGER = logging.getLogger(__name__)
CONF_AUTO_DISCOVER = "auto_discover"
DISCOVERY_TIMEOUT = 30

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
            auto_discover = user_input.pop(CONF_AUTO_DISCOVER, False)
            ip = user_input.get(CONF_IP, "").strip()
            if not all(
                self._validate_time(user_input[key])
                for key in (CONF_NIGHT_START, CONF_NIGHT_END)
            ):
                if not self._validate_time(user_input[CONF_NIGHT_START]):
                    errors[CONF_NIGHT_START] = "invalid_time"
                if not self._validate_time(user_input[CONF_NIGHT_END]):
                    errors[CONF_NIGHT_END] = "invalid_time"
            elif auto_discover:
                try:
                    discovered_ip = await self._async_discover_device()
                except OSError as err:
                    _LOGGER.error("Unable to start Airnut device discovery: %s", err)
                    errors["base"] = "discovery_failed"
                else:
                    if discovered_ip is None:
                        errors["base"] = "device_not_found"
                    else:
                        ip = discovered_ip
            elif not self._validate_ip(ip):
                errors[CONF_IP] = "invalid_ip"

            if not errors:
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
                vol.Optional(CONF_IP, default=""): str,
                vol.Optional(CONF_AUTO_DISCOVER, default=False): bool,
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

    async def _async_discover_device(self) -> str | None:
        """Listen for an unconfigured Airnut device connecting to the server."""
        domain_data = self.hass.data.setdefault(DOMAIN, {})
        lock = domain_data.setdefault("_discovery_lock", asyncio.Lock())
        async with lock:
            server = domain_data.get("server")
            owns_server = server is None
            if owns_server:
                server = AirnutAsyncSocketServer(self.hass, {})
                await server.start()
                domain_data["server"] = server

            keep_server = False
            try:
                excluded_ips = {
                    entry.data[CONF_IP]
                    for entry in self._async_current_entries()
                    if CONF_IP in entry.data
                }
                discovered_ip = await server.async_wait_for_device(
                    DISCOVERY_TIMEOUT, excluded_ips
                )
                keep_server = discovered_ip is not None
                return discovered_ip
            finally:
                if owns_server and not keep_server:
                    await server.stop()
                    domain_data.pop("server", None)
                    if not domain_data:
                        self.hass.data.pop(DOMAIN, None)

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
