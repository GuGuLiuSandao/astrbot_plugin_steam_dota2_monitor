# Steam Dota2 战绩查询插件

本插件是专为 AstrBot 设计的 Dota2 比赛战绩查询插件，支持生成精美的比赛战报图片、查询玩家最近比赛记录，并支持定时推送订阅玩家的最新比赛。

## ✨ 功能特性
- **精美战报生成**：使用本地资源生成 Dota2 比赛结算界面风格的战报图片，包含英雄头像、装备图标、KDA、伤害数据等详细信息。
- **多 API 支持**：优先使用 Steam Web API，自动降级使用 OpenDota API，确保高可用性。
- **订阅推送**：支持订阅多个玩家，定时检查并在有新比赛时自动推送到指定群组。
- **别名系统**：支持为 Steam ID 设置别名，查询时无需记忆复杂的数字 ID。
- **智能缓存**：自动缓存英雄和物品数据，减少网络请求。

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

## ⚙️ 配置

在 AstrBot 管理面板的插件配置中，您可以设置以下选项：

1.  **steam_api_key**: Steam Web API Key，推荐配置以获得更稳定的查询体验。[点击获取](https://steamcommunity.com/dev/apikey)
2.  **alias_map**: 别名映射配置。格式为 `SteamID:别名1,别名2`。
    - 示例：`76561198000000000:小明,xm`
    - 配置后，使用 `/dota2_recent 小明` 等同于使用该 SteamID。
3.  **subscriptions**: 订阅列表。填写需要自动推送战报的玩家 SteamID。
4.  **cron_expression**: 定时检查任务的 Cron 表达式。
    - 默认：`0 0,14,16,18,20,22 * * *` (每天0点、14点、16点...检查)
    - 格式：`分 时 日 月 周` (基于 UTC+8 时间)
5.  **groups**: 推送目标群组列表。
    - 建议使用 `/dota2_bind` 指令自动绑定当前群组，无需手动填写。

## 🎮 指令列表

- **/dota2_match [比赛ID]**
  - 查询单场比赛详情并生成战报图片。
  - 示例：`/dota2_match 7560000000`

- **/dota2_recent [SteamID/别名]**
  - 查询用户最近 5 场比赛记录。
  - 示例：`/dota2_recent 76561198000000000` 或 `/dota2_recent 小明`

- **/dota2_bind**
  - 将当前群组/会话绑定为订阅推送的目标。
  - 需在目标群组中发送此指令。

- **/dota2_check_sub**
  - 手动触发一次订阅检查。
  - 立即检查所有订阅用户是否有新比赛。

## 📦 依赖
- Python 3.8+
- AstrBot 框架
- aiohttp
- Pillow (PIL)
- croniter

## ❓ 常见问题
- **如何获取 Steam 64位 ID？**
  - 您可以在 [SteamID.io](https://steamid.io/) 等网站查询，或在 Dota2 客户端个人资料中查看数字 ID 并进行转换。
- **为什么没有生成图片？**
  - 请检查 `resources` 目录下是否包含 `fonts` 和 `images` 文件夹，且字体文件 `NotoSansHans-Regular.otf` 存在。
- **推送任务不执行？**
  - 请检查日志中是否有 `[Dota2Monitor]` 相关的启动日志。
  - 确保 Cron 表达式格式正确。

---
> 如果本项目对您有帮助，欢迎 Star 支持！
