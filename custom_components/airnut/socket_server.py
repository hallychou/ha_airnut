"""Asynchronous Socket Server for Airnut 1S."""
import asyncio
import json
import logging
import socket
from dataclasses import dataclass
from datetime import datetime, time

from homeassistant.core import HomeAssistant

from .const import (
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_NIGHT_UPDATE,
    CONF_SCAN_INTERVAL,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_NIGHT_UPDATE,
    DEFAULT_SCAN_INTERVAL,
    MAX_SOCKET_BUFFER_SIZE,
    SOCKET_BUFFER_SIZE,
    SOCKET_HOST,
    SOCKET_PORT,
)

_LOGGER = logging.getLogger(__name__)
CLIENT_CLOSE_TIMEOUT = 2


@dataclass
class AirnutDeviceData:
    """Data reported by an Airnut device."""

    temperature: float | None = None
    humidity: float | None = None
    pm25: int | None = None
    co2: int | None = None
    last_update: datetime | None = None


class AirnutAsyncSocketServer:
    """Asynchronous Socket Server to communicate with Airnut 1S devices."""

    def __init__(self, hass: HomeAssistant, config: dict):
        self.hass = hass
        self.config = config
        self._server: asyncio.Server | None = None
        self._clients: dict[asyncio.StreamWriter, str] = {}
        self._client_socket_ids: dict[asyncio.StreamWriter, int | str] = {}
        self._configured_clients: set[asyncio.StreamWriter] = set()
        self._receive_buffers: dict[asyncio.StreamWriter, bytearray] = {}
        self._device_data: dict[str, AirnutDeviceData] = {}
        self._last_scan: dict[str, float] = {}
        self._device_configs: dict[str, dict] = {}
        self._device_connected = asyncio.Event()
        self._scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self._is_running = False
        self._lock = asyncio.Lock()

    @staticmethod
    def _parse_time(time_str: str, default: str) -> time:
        """Parse a time string, falling back to the supplied default."""
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except (TypeError, ValueError):
            _LOGGER.warning("Invalid time format %s, using %s", time_str, default)
            return datetime.strptime(default, "%H:%M").time()

    @classmethod
    def _is_night_time(cls, config: dict) -> bool:
        """Check whether the current local time is in the configured night period."""
        now = datetime.now().time()
        night_start = cls._parse_time(
            config.get(CONF_NIGHT_START, DEFAULT_NIGHT_START), DEFAULT_NIGHT_START
        )
        night_end = cls._parse_time(
            config.get(CONF_NIGHT_END, DEFAULT_NIGHT_END), DEFAULT_NIGHT_END
        )
        if night_start < night_end:
            return night_start <= now < night_end
        return now >= night_start or now < night_end

    @property
    def has_registered_devices(self) -> bool:
        """Return whether any config entry still uses this server."""
        return bool(self._device_configs)

    def register_device(self, ip: str, config: dict) -> None:
        """Register per-device polling options."""
        self._device_configs[ip] = config

    def unregister_device(self, ip: str) -> None:
        """Remove per-device polling state."""
        self._device_configs.pop(ip, None)
        self._last_scan.pop(ip, None)
        self._device_data.pop(ip, None)

    async def start(self) -> None:
        """Start the async socket server."""
        async with self._lock:
            if self._is_running:
                _LOGGER.info("Socket server is already running, skip start")
                return

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((SOCKET_HOST, SOCKET_PORT))
                sock.setblocking(False)
                self._server = await asyncio.start_server(
                    self._handle_client,
                    sock=sock,
                )
                self._is_running = True
                _LOGGER.info("Airnut socket server started on %s:%s", SOCKET_HOST, SOCKET_PORT)
            except OSError as err:
                sock.close()
                _LOGGER.error("Failed to start socket server: %s", err)
                raise

    async def stop(self) -> None:
        """Stop the server and close all client connections."""
        async with self._lock:
            if not self._is_running:
                _LOGGER.info("Socket server is not running, skip stop")
                return

            if self._server is not None:
                self._server.close()
                try:
                    await asyncio.wait_for(
                        self._server.wait_closed(),
                        timeout=CLIENT_CLOSE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timed out waiting for Airnut listening socket to close")
                self._server = None

            for writer in list(self._clients):
                client_ip = self._clients.get(writer, "unknown")
                try:
                    await self._close_writer(writer, client_ip)
                finally:
                    self._clients.pop(writer, None)
                    self._client_socket_ids.pop(writer, None)
                    self._configured_clients.discard(writer)
                    self._receive_buffers.pop(writer, None)

            self._device_data.clear()
            self._last_scan.clear()
            self._is_running = False
            _LOGGER.info("Airnut socket server stopped")

    async def _close_writer(
        self, writer: asyncio.StreamWriter, client_ip: str
    ) -> None:
        """Close a client connection without blocking shutdown indefinitely."""
        writer.close()
        try:
            await asyncio.wait_for(
                writer.wait_closed(), timeout=CLIENT_CLOSE_TIMEOUT
            )
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timed out closing client %s; aborting the connection", client_ip
            )
            writer.transport.abort()
        except (ConnectionError, OSError) as err:
            _LOGGER.debug("Error closing client %s: %s", client_ip, err)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a new Airnut device connection."""
        peer = writer.get_extra_info("peername")
        if not peer:
            _LOGGER.warning("Airnut connection has no peer address")
            await self._close_writer(writer, "unknown")
            return

        client_ip = peer[0]
        self._clients[writer] = client_ip
        self._client_socket_ids.pop(writer, None)
        self._configured_clients.discard(writer)
        self._receive_buffers[writer] = bytearray()
        _LOGGER.info("Airnut device connected: %s", client_ip)

        try:
            while data := await reader.read(SOCKET_BUFFER_SIZE):
                await self._parse_device_data(client_ip, writer, data)
        except (ConnectionError, OSError) as err:
            _LOGGER.error("Error handling client %s: %s", client_ip, err)
        finally:
            self._clients.pop(writer, None)
            self._client_socket_ids.pop(writer, None)
            self._configured_clients.discard(writer)
            self._receive_buffers.pop(writer, None)
            if client_ip not in self._clients.values():
                self._device_data.pop(client_ip, None)
            await self._close_writer(writer, client_ip)

    async def _send_get_command(
        self, writer: asyncio.StreamWriter, socket_id: int | str
    ) -> None:
        """Request the device's current sensor data after login."""
        check_key = f"s_get{socket_id}"
        get_cmd = {
            "sendback_appserver": 100000007,
            "param": {
                "socket_id": 100000007,
                "type": 1,
                "check_key": check_key,
            },
            "p": "get",
            "type": "control",
            "check_key": check_key,
        }

        writer.write(json.dumps(get_cmd).encode("utf-8"))
        await writer.drain()

    async def _send_volume_command(
        self, writer: asyncio.StreamWriter, socket_id: int | str
    ) -> None:
        """Set the device volume after its first valid sensor report."""
        volume_key = f"s_set_volume{socket_id}"
        volume_cmd = {
            "sendback_appserver": 100000007,
            "param": {
                "volume": 0,
                "socket_id": 100000007,
                "check_key": volume_key,
            },
            "volume": 0,
            "p": "set_volume",
            "type": "control",
            "check_key": volume_key,
        }

        writer.write(json.dumps(volume_cmd).encode("utf-8"))
        await writer.drain()

    async def _parse_device_data(
        self,
        client_ip: str,
        writer: asyncio.StreamWriter,
        data: bytes,
    ) -> None:
        """Parse complete JSON messages from the TCP byte stream."""
        buffer = self._receive_buffers[writer]
        buffer.extend(data)
        try:
            raw_data = buffer.decode("utf-8")
        except UnicodeDecodeError as err:
            if err.reason == "unexpected end of data" and err.end == len(buffer):
                if len(buffer) > MAX_SOCKET_BUFFER_SIZE:
                    _LOGGER.warning(
                        "Discarding oversized incomplete UTF-8 data from %s", client_ip
                    )
                    buffer.clear()
                return
            _LOGGER.warning("Invalid UTF-8 data from %s", client_ip)
            buffer.clear()
            return

        decoder = json.JSONDecoder()
        position = 0
        while position < len(raw_data):
            while position < len(raw_data) and raw_data[position].isspace():
                position += 1
            if position == len(raw_data):
                break

            try:
                json_data, end = decoder.raw_decode(raw_data, position)
            except json.JSONDecodeError as err:
                delimiter = raw_data.find("\n\r", position)
                if delimiter >= 0:
                    _LOGGER.warning(
                        "Discarding invalid JSON message from %s: %s", client_ip, err
                    )
                    position = delimiter + 2
                    continue
                if len(buffer) > MAX_SOCKET_BUFFER_SIZE:
                    _LOGGER.warning(
                        "Discarding oversized incomplete message from %s", client_ip
                    )
                    buffer.clear()
                break

            if isinstance(json_data, dict):
                await self._handle_device_message(client_ip, writer, json_data)
            else:
                _LOGGER.warning("Ignoring non-object message from %s", client_ip)
            position = end

        if position:
            consumed = len(raw_data[:position].encode("utf-8"))
            del buffer[:consumed]

    @staticmethod
    def _socket_id_from_imei(json_data: dict) -> str | None:
        params = json_data.get("param")
        imei = params.get("imei") if isinstance(params, dict) else None
        if not isinstance(imei, str):
            return None

        digits = "".join(char for char in imei if char.isascii() and char.isdigit())
        return digits[-5:] if len(digits) >= 5 else None

    async def _handle_device_message(
        self,
        client_ip: str,
        writer: asyncio.StreamWriter,
        json_data: dict,
    ) -> None:
        """Handle a decoded message from an Airnut device."""
        if json_data.get("p") == "log_in":
            socket_id = self._socket_id_from_imei(json_data)
            if socket_id is None:
                _LOGGER.warning("Login message from %s has no valid IMEI", client_ip)
                return

            self._client_socket_ids[writer] = socket_id
            self._device_connected.set()
            login_resp = {
                "type": "client",
                "socket_id": socket_id,
                "result": 0,
                "p": "log_in",
            }
            writer.write(json.dumps(login_resp).encode("utf-8"))
            await writer.drain()
            await self._send_get_command(writer, socket_id)
        elif json_data.get("p") == "post":
            try:
                indoor_data = json_data["param"]["indoor"]
                device_data = AirnutDeviceData(
                    temperature=round(float(indoor_data["t"]), 1),
                    humidity=round(float(indoor_data["h"]), 1),
                    pm25=int(indoor_data["pm25"]),
                    co2=int(indoor_data["co2"]),
                    last_update=datetime.now(),
                )
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.warning("Invalid sensor data from %s: %s", client_ip, err)
                return

            self._device_data[client_ip] = device_data
            _LOGGER.debug("Updated data for %s: %s", client_ip, device_data)
            socket_id = self._client_socket_ids.get(writer)
            if socket_id is not None and writer not in self._configured_clients:
                await self._send_volume_command(writer, socket_id)
                self._configured_clients.add(writer)

    async def update_device_data(self, device_ip: str) -> None:
        """Request updated data from a device when its scan interval expires."""
        now = asyncio.get_running_loop().time()
        config = self._device_configs.get(device_ip, self.config)
        scan_interval = config.get(CONF_SCAN_INTERVAL, self._scan_interval)
        last_scan = self._last_scan.get(device_ip, float("-inf"))
        if now - last_scan < scan_interval:
            return

        if not config.get(CONF_NIGHT_UPDATE, DEFAULT_NIGHT_UPDATE) and self._is_night_time(config):
            _LOGGER.debug("Skipping update for %s during night time", device_ip)
            return

        writers = [
            (writer, socket_id)
            for writer, client_ip in self._clients.items()
            if client_ip == device_ip
            and (socket_id := self._client_socket_ids.get(writer)) is not None
        ]
        if not writers:
            return

        self._last_scan[device_ip] = now
        for writer, socket_id in writers:
            check_key = f"s_get{socket_id}"
            get_cmd = {
                "sendback_appserver": 100000007,
                "param": {
                    "socket_id": 100000007,
                    "type": 1,
                    "check_key": check_key,
                },
                "p": "get",
                "type": "control",
                "check_key": check_key,
            }
            try:
                writer.write(json.dumps(get_cmd).encode("utf-8"))
                await writer.drain()
            except (ConnectionError, OSError) as err:
                _LOGGER.warning("Failed to send get command to %s: %s", device_ip, err)
                self._clients.pop(writer, None)
                self._client_socket_ids.pop(writer, None)
                self._configured_clients.discard(writer)
                self._receive_buffers.pop(writer, None)

    def get_device_data(self, ip: str) -> AirnutDeviceData | None:
        """Get latest data for a specific device IP."""
        return self._device_data.get(ip)

    async def async_wait_for_device(
        self, timeout: float, excluded_ips: set[str] | None = None
    ) -> str | None:
        """Wait for a logged-in Airnut device and return its IP address."""
        excluded_ips = excluded_ips or set()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            self._device_connected.clear()
            for writer, client_ip in self._clients.items():
                if (
                    client_ip not in excluded_ips
                    and writer in self._client_socket_ids
                ):
                    return client_ip

            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                await asyncio.wait_for(self._device_connected.wait(), remaining)
            except asyncio.TimeoutError:
                return None
