# Airnut 1S - Home Assistant 集成

[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.8%2B-blue)](https://www.home-assistant.io/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

适用于 Home Assistant 的 Airnut 1S（空气果1S）集成，支持自动获取温度、湿度、PM2.5、CO₂ 数据，完全本地化运行，无需依赖第三方服务器。

## 功能特性
✅ 异步 Socket 服务架构：基于 HA 异步IO模型实现 Socket 通信，无阻塞占用 HA 主线程，性能更优  
✅ 标准化 Config Flow 配置流程：提供可视化UI配置向导，支持设备IP、扫描间隔、夜间更新策略自定义配置  
✅ 一键批量创建实体：单设备IP配置即可自动生成温度/湿度/PM2.5/CO₂ 四个传感器实体，无需逐个添加  
✅ 遵循 HA 原生规范：严格适配 SensorEntity 标准，原生 device_class、测量单位及图标自动匹配，无需手动配置  
✅ 本地化数据流转：通过 DNS 劫持实现设备数据直连 HA，全程内网通信，数据不经过外网，隐私更安全  
✅ 灵活的更新策略：支持自定义数据扫描间隔，可配置夜间更新开关，平衡数据实时性与设备功耗  
✅ 端口复用优化：内置 SO_REUSEADDR/SO_REUSEPORT 端口复用逻辑，避免 10511 端口占用导致的启动失败  
✅ 高版本兼容：完美适配 Home Assistant 2024.8+ 版本，兼容 HA OS/Supervised/Docker/手动安装等部署方式

## 前置条件
### 1. 网络环境要求
- Airnut 1S 设备与 Home Assistant 处于同一局域网
- 路由器支持 DNS 劫持（用于将 Airnut 1S 的云端请求重定向到 HA）

### 2. DNS 劫持配置
需在路由器中配置 DNS 劫持，将 `apn.airnut.com` 解析到 Home Assistant 的内网 IP（如 `192.168.31.100`）：
- 大部分路由器（如 OpenWRT/梅林/华硕）可在「自定义 DNS 解析」「本地域名」中配置
- 若路由器不支持，可使用 AdGuard Home / Pi-hole 实现 DNS 劫持

### 3. Airnut 1S 设备配置
- 确保 Airnut 1S 已完成 WiFi 配置，且与 HA 连接同一网络
- 设备指示灯为绿色（正常工作状态）

## 安装方法
### 方法1：手动安装（推荐）
1. 在 Home Assistant 的 `config` 目录下创建 `custom_components/airnut` 文件夹
2. 将集成所有文件放入该目录
3. 重启 Home Assistant 核心

### 方法2：HACS 安装（待上架）
暂未上架 HACS，建议先使用手动安装方式。

## 配置步骤
1. 重启 HA 后，进入「设置 → 设备与服务 → 添加集成」
2. 搜索「Airnut 1S」并选择
3. 填写配置项：
   - **设备IP**：Airnut 1S 的内网 IP（如 `192.168.31.113`）
   - **扫描间隔**（可选）：数据更新间隔（默认 600 秒，最小 30 秒）
   - **夜间时段**（可选）：夜间开始/结束时间（默认 23:00 - 06:00）
   - **夜间更新**（可选）：是否在夜间继续更新数据（默认开启）
4. 提交后，HA 会自动创建 4 个传感器实体，并归属到 `Airnut 1S (设备IP)` 设备条目下

## 传感器实体说明
| 实体名称                | 设备类 (device_class) | 单位      | 说明           |
|-------------------------|-----------------------|-----------|----------------|
| Airnut 1S Temperature   | temperature           | °C        | 温度传感器     |
| Airnut 1S Humidity      | humidity              | %         | 湿度传感器     |
| Airnut 1S PM2.5         | pm25                  | µg/m³     | PM2.5 传感器   |
| Airnut 1S CO2           | co2                   | ppm       | CO₂ 传感器     |

## 配置参数说明
| 参数名          | 类型    | 默认值  | 说明                       |
|-----------------|---------|---------|----------------------------|
| ip              | 字符串  | -       | Airnut 1S 内网 IP（必填）|
| scan_interval   | 整数    | 600     | 数据扫描间隔（秒）|
| night_start     | 字符串  | 23:00   | 夜间时段开始时间（HH:MM）|
| night_end       | 字符串  | 06:00   | 夜间时段结束时间（HH:MM）|
| night_update    | 布尔值  | True    | 夜间是否更新数据           |

## 常见问题排查
### Q1: 添加集成时提示「already_configured」
- 原因：HA 后台残留旧配置条目
- 解决：
  1. 开启 HA 高级模式，进入「开发者工具 → 动作」
  2. 调用 `config_entries.async_remove` 动作，删除 Airnut 相关 entry_id
  3. 或直接编辑 `config/.storage/core.config_entries` 删除相关条目

### Q2: 传感器实体显示但无数据
- 检查 DNS 劫持是否生效：在 HA 终端执行 `nslookup apn.airnut.com`，确认返回 HA 内网 IP
- 检查 Socket 服务端口（10511）是否被占用：`netstat -tulpn | grep 10511`
- 重启 Airnut 1S 设备，确保设备重新连接 WiFi 并解析 DNS

### Q3: 端口占用错误（Errno 98）
- 原因：10511 端口被其他进程占用
- 解决：
  1. 查找占用进程：`ss -tulpn | grep 10511`
  2. 终止进程：`kill -9 进程ID`
  3. 重启 HA 即可自动恢复

## 数据流转说明
1. Airnut 1S 向 `apn.airnut.com` 发送数据上报请求（被 DNS 劫持到 HA）
2. HA 内置的异步 Socket 服务接收并解析包含全量数据的数据包
3. 服务端统一存储温度、湿度、PM2.5、CO₂ 数据
4. 四个传感器从同一数据源同步更新，保证数据一致性

## 兼容性
- Home Assistant 版本：2024.8+
- Airnut 设备型号：Airnut 1S
- 运行环境：HA OS / Supervised / Docker / 手动安装

## 许可证
本项目基于 MIT 许可证开源。

## 免责声明
- 本集成仅用于个人非商业使用
- 作者不对设备损坏、数据丢失等问题承担责任
- 使用前请确保符合相关法律法规