"""Constants for Airnut 1S integration (启用device_class默认图标)."""
from homeassistant.components.sensor import SensorDeviceClass

# 集成域名
DOMAIN = "airnut"

# 配置项常量
CONF_IP = "ip"
CONF_SENSOR_TYPE = "sensor_type"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"
CONF_NIGHT_UPDATE = "night_update"

# 默认配置
DEFAULT_SCAN_INTERVAL = 600
DEFAULT_NIGHT_START = "23:00"
DEFAULT_NIGHT_END = "06:00"
DEFAULT_NIGHT_UPDATE = False

# Socket配置
SOCKET_HOST = "0.0.0.0"
SOCKET_PORT = 10511
SOCKET_BUFFER_SIZE = 1024

# 传感器类型规范配置（移除手动icon，使用device_class默认图标）
SENSOR_TYPES = {
    "temperature": {
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "native_unit_of_measurement": "°C"
        # 移除icon字段，启用HA默认图标
    },
    "humidity": {
        "name": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "native_unit_of_measurement": "%"
        # 移除icon字段
    },
    "pm25": {
        "name": "PM2.5",
        "device_class": SensorDeviceClass.PM25,
        "native_unit_of_measurement": "µg/m³"
        # 移除icon字段
    },
    "co2": {
        "name": "CO2",
        "device_class": SensorDeviceClass.CO2,
        "native_unit_of_measurement": "ppm"
        # 移除icon字段
    },
}

# 集成平台定义
PLATFORMS = ["sensor"]