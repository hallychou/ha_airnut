"""Constants for Airnut 1S integration."""
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass  # 新增StateClass导入

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
DEFAULT_NIGHT_UPDATE = True

# Socket配置
SOCKET_HOST = "0.0.0.0"
SOCKET_PORT = 10511
SOCKET_BUFFER_SIZE = 1024

# 传感器类型规范配置（新增state_class）
SENSOR_TYPES = {
    "temperature": {
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "native_unit_of_measurement": "°C",
        "state_class": SensorStateClass.MEASUREMENT  # 新增状态类
    },
    "humidity": {
        "name": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "native_unit_of_measurement": "%",
        "state_class": SensorStateClass.MEASUREMENT
    },
    "pm25": {
        "name": "PM2.5",
        "device_class": SensorDeviceClass.PM25,
        "native_unit_of_measurement": "µg/m³",
        "state_class": SensorStateClass.MEASUREMENT
    },
    "co2": {
        "name": "CO2",
        "device_class": SensorDeviceClass.CO2,
        "native_unit_of_measurement": "ppm",
        "state_class": SensorStateClass.MEASUREMENT
    },
}

# 集成平台定义
PLATFORMS = ["sensor"]