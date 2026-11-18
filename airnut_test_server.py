"""Standalone TCP server for testing communication with Airnut 1S devices."""

import argparse
import asyncio
import json
import logging

LOGGER = logging.getLogger("airnut_test_server")
MAX_MESSAGE_SIZE = 64 * 1024
READ_SIZE = 1024


class AirnutTestServer:
    """Accept Airnut device connections and emulate the integration protocol."""

    def __init__(self) -> None:
        self._configured_clients: set[asyncio.StreamWriter] = set()
        self._client_socket_ids: dict[asyncio.StreamWriter, int | str] = {}

    @staticmethod
    def _socket_id_from_imei(message: dict) -> str | None:
        params = message.get("param")
        imei = params.get("imei") if isinstance(params, dict) else None
        if not isinstance(imei, str):
            return None

        digits = "".join(char for char in imei if char.isascii() and char.isdigit())
        return digits[-5:] if len(digits) >= 5 else None

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        client = str(peer[0]) if peer else "unknown"
        buffer = bytearray()
        LOGGER.info("设备已连接：%s", client)

        try:
            while data := await reader.read(READ_SIZE):
                buffer.extend(data)
                await self._process_buffer(client, buffer, writer)
        except (ConnectionError, OSError) as err:
            LOGGER.warning("与设备 %s 通信失败：%s", client, err)
        finally:
            self._configured_clients.discard(writer)
            self._client_socket_ids.pop(writer, None)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError) as err:
                LOGGER.debug("关闭设备 %s 的连接失败：%s", client, err)
            LOGGER.info("设备已断开：%s", client)

    async def _process_buffer(
        self, client: str, buffer: bytearray, writer: asyncio.StreamWriter
    ) -> None:
        try:
            raw_data = buffer.decode("utf-8")
        except UnicodeDecodeError as err:
            if err.reason == "unexpected end of data" and err.end == len(buffer):
                if len(buffer) > MAX_MESSAGE_SIZE:
                    LOGGER.warning("设备 %s 的消息超过大小限制，已丢弃", client)
                    buffer.clear()
                return
            LOGGER.warning("设备 %s 发送了无效 UTF-8 数据，已丢弃", client)
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
                message, end = decoder.raw_decode(raw_data, position)
            except json.JSONDecodeError:
                delimiter = raw_data.find("\n\r", position)
                if delimiter >= 0:
                    LOGGER.warning("设备 %s 发送了无效 JSON 消息，已跳过", client)
                    position = delimiter + 2
                    continue
                if len(buffer) > MAX_MESSAGE_SIZE:
                    LOGGER.warning("设备 %s 的消息超过大小限制，已丢弃", client)
                    buffer.clear()
                break

            if isinstance(message, dict):
                await self._handle_message(client, message, writer)
            else:
                LOGGER.warning("忽略设备 %s 发送的非 JSON 对象消息", client)
            position = end

        if position:
            del buffer[: len(raw_data[:position].encode("utf-8"))]

    async def _send(self, writer: asyncio.StreamWriter, message: dict) -> None:
        writer.write(json.dumps(message).encode("utf-8"))
        await writer.drain()
        LOGGER.info("发送：%s", json.dumps(message, ensure_ascii=False))

    async def _handle_message(
        self, client: str, message: dict, writer: asyncio.StreamWriter
    ) -> None:
        LOGGER.info("收到 %s：%s", client, json.dumps(message, ensure_ascii=False))
        if message.get("p") == "log_in":
            socket_id = self._socket_id_from_imei(message)
            if socket_id is None:
                LOGGER.warning("设备 %s 登录消息中没有有效的 IMEI", client)
                return
            LOGGER.info("使用 IMEI 尾部五位作为 socket_id：%s", socket_id)

            await self._send(
                writer,
                {
                    "type": "client",
                    "socket_id": socket_id,
                    "result": 0,
                    "p": "log_in",
                },
            )
            self._client_socket_ids[writer] = socket_id
            check_key = f"s_get{socket_id}"
            await self._send(
                writer,
                {
                    "sendback_appserver": 100000007,
                    "param": {
                        "socket_id": 100000007,
                        "type": 1,
                        "check_key": check_key,
                    },
                    "p": "get",
                    "type": "control",
                    "check_key": check_key,
                },
            )
        elif message.get("p") == "get_weather":
            LOGGER.warning(
                "设备 %s 请求 get_weather；当前协议没有定义天气响应格式，未发送回复",
                client,
            )
        elif message.get("p") == "post":
            try:
                indoor = message["param"]["indoor"]
                readings = {
                    "temperature": round(float(indoor["t"]), 1),
                    "humidity": round(float(indoor["h"]), 1),
                    "pm25": int(indoor["pm25"]),
                    "co2": int(indoor["co2"]),
                }
            except (KeyError, TypeError, ValueError) as err:
                LOGGER.warning("设备 %s 的传感器数据无效：%s", client, err)
                return

            LOGGER.info(
                "传感器数据：温度 %s °C，湿度 %s%%，PM2.5 %s µg/m³，CO₂ %s ppm",
                readings["temperature"],
                readings["humidity"],
                readings["pm25"],
                readings["co2"],
            )
            socket_id = self._client_socket_ids.get(writer)
            if socket_id is None:
                LOGGER.info("尚未收到有效登录消息，不发送音量设置命令")
            elif writer not in self._configured_clients:
                volume_key = f"s_set_volume{socket_id}"
                await self._send(
                    writer,
                    {
                        "sendback_appserver": 100000007,
                        "param": {
                            "volume": 100,
                            "socket_id": 100000007,
                            "check_key": volume_key,
                        },
                        "volume": 100,
                        "p": "set_volume",
                        "type": "control",
                        "check_key": volume_key,
                    },
                )
                self._configured_clients.add(writer)


async def run_server(host: str, port: int) -> None:
    protocol = AirnutTestServer()
    server = await asyncio.start_server(protocol.handle_client, host, port)
    addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    LOGGER.info("Airnut 测试服务已启动：%s", addresses)
    async with server:
        await server.serve_forever()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行独立的 Airnut 1S TCP 测试服务端。"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="监听地址（默认 0.0.0.0，允许局域网设备连接）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=10511,
        help="监听端口（默认 10511）",
    )
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port 必须在 0 到 65535 之间")
    return args


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args(argv)
    try:
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        LOGGER.info("Airnut 测试服务已停止")


if __name__ == "__main__":
    main()
