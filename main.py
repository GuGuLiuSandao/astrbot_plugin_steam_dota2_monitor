from astrbot.api.all import *
from .dota2_monitor import Dota2Monitor
from .image_renderer import MatchRenderer
import os

@register("steam_dota2_monitor", "Trae", "Dota2 比赛查询插件", "0.1.0", "https://github.com/TraeAI/astrbot_plugin_steam_dota2_monitor")
class SteamDota2Monitor(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_key = self.config.get("steam_api_key", "")
        self.heroes_map = {}
        self.items_map = {}
        self.renderer = MatchRenderer(os.path.join(os.path.dirname(__file__), "resources"))

    async def _ensure_resources(self):
        if not self.heroes_map or not self.items_map:
            monitor = Dota2Monitor(self.api_key)
            await monitor.load_heroes()
            await monitor.load_items()
            self.heroes_map = monitor.heroes_map
            self.items_map = monitor.items_map

    @command("dota2_match")
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
        
        # 获取详细数据 (包含玩家昵称等)
        details = await monitor.get_enriched_match_details(match_id)
        
        if not details:
            yield event.plain_result(f"无法获取比赛 {match_id} 的详情。")
            return

        try:
            # Render image locally
            img_bytes = await self.renderer.render(details)
            
            # Save to temp file
            temp_dir = os.path.join(os.path.dirname(__file__), "temp")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            temp_path = os.path.join(temp_dir, f"match_{match_id}.jpg")
            with open(temp_path, "wb") as f:
                f.write(img_bytes)
                
            yield event.make_result().file_image(temp_path)
            
        except Exception as e:
            # Fallback
            text_result = monitor.format_match_details(details)
            yield event.plain_result(f"图片生成失败 ({e})，已回退到文本模式：\n{text_result}")

    @command("dota2_recent")
    async def query_recent(self, event: AstrMessageEvent, steam_id: str):
        """查询用户最近5场比赛。格式: /dota2_recent <SteamID_64>"""
        if not self.api_key:
            yield event.plain_result("请先在插件配置中设置 Steam API Key。")
            return

        if not steam_id:
            yield event.plain_result("请提供 Steam 64位 ID。")
            return

        await self._ensure_resources()
        
        yield event.plain_result(f"正在查询用户 {steam_id} 的最近5场比赛，请稍候...")
        
        monitor = Dota2Monitor(self.api_key, steam_id)
        monitor.heroes_map = self.heroes_map
        monitor.items_map = self.items_map
        
        # 获取详细数据列表
        matches_details = await monitor.get_recent_matches_details(limit=5)
        
        if not matches_details:
            yield event.plain_result("未找到比赛记录。")
            return
            
        temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        for i, details in enumerate(matches_details):
            try:
                # Render image locally
                img_bytes = await self.renderer.render(details)
                
                match_id = details.get('match_id', 'unknown')
                temp_path = os.path.join(temp_dir, f"recent_{match_id}.jpg")
                
                with open(temp_path, "wb") as f:
                    f.write(img_bytes)
                    
                # 发送图片
                yield event.make_result().file_image(temp_path)
                
            except Exception as e:
                # Fallback to text if rendering fails
                text_result = monitor.format_match_details(details)
                yield event.plain_result(f"比赛 {details.get('match_id')} 图片生成失败 ({e})，回退到文本模式：\n{text_result}")
