"""Asynchronous Socket Server for Airnut 1S."""
import asyncio
import json
import logging
import socket  # 新增：导入socket模块
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
    SOCKET_BUFFER_SIZE,
    SOCKET_HOST,
    SOCKET_PORT,
)

_LOGGER = logging.getLogger(__name__)

@dataclass
class AirnutDeviceData:
    """Dataclass for Airnut device data."""
    temperature: float | None = None
    humidity: float | None = None
    pm25: int | None = None
    co2: int | None = None
    last_update: datetime | None = None

class AirnutAsyncSocketServer:
    """Asynchronous Socket Server to communicate with Airnut 1S devices."""

    _instance = None  # 新增：单例模式，确保只启动一个服务
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式：确保全局只有一个Socket服务实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, hass: HomeAssistant, config: dict):
        self.hass = hass
        self.config = config
        self._server: asyncio.Server | None = None
        self._clients: dict[asyncio.StreamWriter, str] = {}  # writer -> device IP
        self._device_data: dict[str, AirnutDeviceData] = {}  # device IP -> data
        self._last_scan: datetime = datetime.min
        self._scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self._night_start = self._parse_time(config.get(CONF_NIGHT_START, DEFAULT_NIGHT_START))
        self._night_end = self._parse_time(config.get(CONF_NIGHT_END, DEFAULT_NIGHT_END))
        self._night_update = config.get(CONF_NIGHT_UPDATE, DEFAULT_NIGHT_UPDATE)
        self._is_running = False  # 新增：标记服务是否运行

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parse time string (HH:MM) to time object."""
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            _LOGGER.warning("Invalid time format %s, using default", time_str)
            return datetime.strptime(DEFAULT_NIGHT_START, "%H:%M").time()

    def _is_night_time(self) -> bool:
        """Check if current time is in night period."""
        now = datetime.now().time()
        if self._night_start < self._night_end:
            return self._night_start <= now <= self._night_end
        # Handle overnight (e.g. 23:00 to 06:00)
        return now >= self._night_start or now <= self._night_end

    async def start(self):
        """Start the async socket server (增加端口复用+避免重复启动)"""
        async with self._lock:
            if self._is_running:
                _LOGGER.info("Socket server is already running, skip start")
                return

            try:
                # 新增：创建socket并设置端口复用（核心修复端口占用）
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                sock.bind((SOCKET_HOST, SOCKET_PORT))
                sock.setblocking(False)

                # 使用自定义socket启动server，而非直接绑定端口
                self._server = await asyncio.start_server(
                    self._handle_client,
                    sock=sock  # 传入已配置的socket
                )
                self._is_running = True
                _LOGGER.info("Airnut socket server started on %s:%s (port reuse enabled)", SOCKET_HOST, SOCKET_PORT)
            except OSError as e:
                _LOGGER.error("Failed to start socket server: %s", e)
                # 新增：释放socket资源
                if 'sock' in locals():
                    sock.close()
                raise

    async def stop(self):
        """Stop the server and close all client connections (完善停止逻辑)"""
        async with self._lock:
            if not self._is_running:
                _LOGGER.info("Socket server is not running, skip stop")
                return

            # 1. 关闭server
            if self._server:
                self._server.close()
                await self._server.wait_closed()
                self._server = None

            # 2. 关闭所有客户端连接（强制关闭）
            for writer in list(self._clients.keys()):
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception as e:
                    _LOGGER.warning("Failed to close client connection: %s", e)
                finally:
                    if writer in self._clients:
                        del self._clients[writer]

            # 3. 清空数据+标记服务停止
            self._device_data.clear()
            self._is_running = False
            _LOGGER.info("Socket server stopped (port released)")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle new client connection (Airnut device)."""
        client_ip = writer.get_extra_info("peername")[0]
        self._clients[writer] = client_ip
        _LOGGER.info("Airnut device connected: %s", client_ip)

        # Initial handshake with device
        await self._send_initial_commands(writer)

        try:
            while True:
                data = await reader.read(SOCKET_BUFFER_SIZE)
                if not data:
                    break
                await self._parse_device_data(client_ip, data)
        except asyncio.IncompleteReadError:
            _LOGGER.debug("Client %s disconnected", client_ip)
        except Exception as e:
            _LOGGER.error("Error handling client %s: %s", client_ip, e)
        finally:
            del self._clients[writer]
            writer.close()
            await writer.wait_closed()

    async def _send_initial_commands(self, writer: asyncio.StreamWriter):
        """Send initial handshake commands to Airnut device."""
        volume_cmd = {
            "sendback_appserver": 100000007,
            "param": {"volume": 0, "socket_id": 100000007, "check_key": "s_set_volume19085"},
            "volume": 0,
            "p": "set_volume",
            "type": "control",
            "check_key": "s_set_volume19085",
        }
        get_cmd = {
            "sendback_appserver": 100000007,
            "param": {"socket_id": 100000007, "type": 1, "check_key": "s_get19085"},
            "p": "get",
            "type": "control",
            "check_key": "s_get19085",
        }

        try:
            writer.write(json.dumps(volume_cmd).encode("utf-8"))
            await writer.drain()
            writer.write(json.dumps(get_cmd).encode("utf-8"))
            await writer.drain()
        except Exception as e:
            _LOGGER.error("Failed to send initial commands: %s", e)

    async def _parse_device_data(self, client_ip: str, data: bytes):
        """Parse data received from Airnut device."""
        try:
            raw_data = data.decode("utf-8").strip()
            for line in raw_data.split("\n\r"):
                if not line:
                    continue
                json_data = json.loads(line)
                if json_data.get("p") == "log_in":
                    # Respond to login request
                    login_resp = {"type": "client", "socket_id": 18567, "result": 0, "p": "log_in"}
                    writer = next(w for w, ip in self._clients.items() if ip == client_ip)
                    writer.write(json.dumps(login_resp).encode("utf-8"))
                    await writer.drain()
                elif json_data.get("p") == "post":
                    # Parse sensor data
                    indoor_data = json_data["param"]["indoor"]
                    device_data = AirnutDeviceData(
                        temperature=round(float(indoor_data["t"]), 1),
                        humidity=round(float(indoor_data["h"]), 1),
                        pm25=int(indoor_data["pm25"]),
                        co2=int(indoor_data["co2"]),
                        last_update=datetime.now(),
                    )
                    self._device_data[client_ip] = device_data
                    _LOGGER.debug("Updated data for %s: %s", client_ip, device_data)
        except json.JSONDecodeError:
            _LOGGER.warning("Invalid JSON data from %s: %s", client_ip, data)
        except KeyError as e:
            _LOGGER.warning("Missing key in device data: %s", e)

    async def update_device_data(self):
        """Poll all connected devices for latest data (per scan interval)."""
        now = datetime.now()
        if (now - self._last_scan).total_seconds() < self._scan_interval:
            return

        # Skip update if night time and night update is disabled
        if not self._night_update and self._is_night_time():
            _LOGGER.debug("Skipping update (night time)")
            return

        self._last_scan = now
        get_cmd = {
            "sendback_appserver": 100000007,
            "param": {"socket_id": 100000007, "type": 1, "check_key": "s_get19085"},
            "p": "get",
            "type": "control",
            "check_key": "s_get19085",
        }

        # Send get command to all connected clients
        for writer in list(self._clients.keys()):
            try:
                writer.write(json.dumps(get_cmd).encode("utf-8"))
                await writer.drain()
            except Exception as e:
                _LOGGER.warning("Failed to send get command to %s: %s", self._clients[writer], e)
                del self._clients[writer]

    def get_device_data(self, ip: str) -> AirnutDeviceData | None:
        """Get latest data for a specific device IP."""
        return self._device_data.get(ip)