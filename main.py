from astrbot.api.all import *
from .dota2_monitor import Dota2Monitor

@register("steam_dota2_monitor", "Trae", "Dota2 比赛查询插件", "0.1.0", "https://github.com/TraeAI/astrbot_plugin_steam_dota2_monitor")
class SteamDota2Monitor(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_key = self.config.get("steam_api_key", "")
        self.heroes_map = {}
        self.items_map = {}

    async def _ensure_resources(self):
        if not self.heroes_map or not self.items_map:
            monitor = Dota2Monitor(self.api_key)
            await monitor.load_heroes()
            await monitor.load_items()
            self.heroes_map = monitor.heroes_map
            self.items_map = monitor.items_map

    @filter.command("dota2_match")
    async def query_match(self, event: AstrMessageEvent, match_id: str):
        """查询单场比赛详情。格式: /dota2_match <match_id>"""
        if not self.api_key:
            yield event.plain_result("请先在插件配置中设置 Steam API Key。")
            return
            
        if not match_id:
            yield event.plain_result("请提供比赛 ID。")
            return

        await self._ensure_resources()
        
        monitor = Dota2Monitor(self.api_key)
        monitor.heroes_map = self.heroes_map
        monitor.items_map = self.items_map
        
        result = await monitor.get_match_details_str(match_id)
        yield event.plain_result(result)

    @filter.command("dota2_recent")
    async def query_recent(self, event: AstrMessageEvent, steam_id: str):
        """查询用户最近5场比赛。格式: /dota2_recent <SteamID_64>"""
        if not self.api_key:
            yield event.plain_result("请先在插件配置中设置 Steam API Key。")
            return

        if not steam_id:
            yield event.plain_result("请提供 Steam 64位 ID。")
            return

        await self._ensure_resources()
        
        monitor = Dota2Monitor(self.api_key, steam_id)
        monitor.heroes_map = self.heroes_map
        monitor.items_map = self.items_map
        
        result = await monitor.get_recent_matches_str()
        yield event.plain_result(result)
