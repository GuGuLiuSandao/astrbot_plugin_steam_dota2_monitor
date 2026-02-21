# Steam Dota2 战绩查询插件

本插件是专为 AstrBot 设计的 Dota2 比赛战绩查询插件，支持查询单场比赛详情和玩家最近比赛记录。通过 Steam Web API 和 OpenDota API 获取数据，提供详细的比赛数据分析。

## 功能特性
- **单场比赛查询**：支持通过比赛 ID 查询详细战绩，包括玩家 KDA、补刀、金钱/经验、英雄伤害、建筑伤害及出装信息。
- **最近比赛记录**：支持查询指定玩家（Steam 64位 ID）最近 5 场比赛的概况。
- **双 API 支持**：优先使用 Steam Web API，失败时自动降级使用 OpenDota API，确保高可用性。
- **智能缓存**：自动缓存英雄和物品数据，减少网络请求，提升响应速度。

## 🛠️ 安装

### 本地安装
1. 将本项目 clone 到 AstrBot 的 `data/plugins/` 目录下。
2. 重启 AstrBot。

### Docker 安装
如果您使用 Docker 运行 AstrBot，可以通过挂载目录的方式安装此插件：

**使用 Docker CLI:**
```bash
docker run -v /宿主机路径/astrbot_plugin_steam_dota2_monitor:/AstrBot/data/plugins/astrbot_plugin_steam_dota2_monitor ...
```

**使用 Docker Compose:**
在 `docker-compose.yml` 的 `volumes` 中添加：
```yaml
volumes:
  - ./astrbot_plugin_steam_dota2_monitor:/AstrBot/data/plugins/astrbot_plugin_steam_dota2_monitor
```
注意：请确保容器内的路径 `/AstrBot/data/plugins/` 是正确的插件目录（取决于您的 AstrBot 容器工作目录配置）。

## ⚙️ 配置
1. 在 AstrBot 网页后台的插件配置中填写 `steam_api_key`：[点击获取](https://steamcommunity.com/dev/apikey)
2. 在群聊或私聊中输入指令即可使用。

## 指令列表
- `/dota2_match [比赛ID]`
  - 查询单场比赛详情。
  - 示例：`/dota2_match 7560000000`
- `/dota2_recent [Steam64位ID]`
  - 查询用户最近 5 场比赛。
  - 示例：`/dota2_recent 76561198000000000`

## 依赖
- Python 3.8+
- AstrBot 框架
- httpx

## 常见问题
- **如何获取 Steam 64位 ID？**
  - 您可以在 [SteamID.io](https://steamid.io/) 等网站通过您的 Steam 个人资料链接查询到的 `steamID64` 即为所需的 ID。
- **为什么查询失败？**
  - 请检查 API Key 是否正确配置。
  - 检查玩家是否开启了“公开比赛数据”选项（在 Dota2 客户端设置中）。
  - 部分比赛可能因过于久远而无法获取详细数据。

---
> 如果本项目对您有帮助，欢迎 Star 支持！
