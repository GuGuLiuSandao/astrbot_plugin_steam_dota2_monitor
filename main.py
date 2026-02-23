from astrbot.api.all import *
from astrbot.api.message_components import Image, Plain
from .dota2_monitor import Dota2Monitor
from .image_renderer import MatchRenderer
import os
import asyncio
import time
import json
import aiohttp
from croniter import croniter
from datetime import datetime, timedelta, timezone

@register("steam_dota2_monitor", "Trae", "Dota2 比赛查询插件", "0.1.0", "https://github.com/TraeAI/astrbot_plugin_steam_dota2_monitor")
class SteamDota2Monitor(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_key = self.config.get("steam_api_key", "")
        self.heroes_map = {}
        self.items_map = {}
        self.renderer = MatchRenderer(os.path.join(os.path.dirname(__file__), "resources"))
        
        # 解析别名配置
        self.alias_map = {}
        self._parse_aliases()
        
        # 启动订阅任务
        self.sub_task = asyncio.create_task(self._subscription_loop())

    def _parse_aliases(self):
        self.alias_map = {}
        self.steam_id_to_aliases = {}
        alias_list = self.config.get("alias_map", [])
        if not alias_list:
            return
            
        for item in alias_list:
            # 格式: SteamID:别名1,别名2
            if ":" in item:
                steam_id, aliases_str = item.split(":", 1)
                steam_id = steam_id.strip()
                aliases = [a.strip() for a in aliases_str.split(",")]
                
                self.steam_id_to_aliases[steam_id] = aliases
                for alias in aliases:
                    # 统一转换为小写，支持大小写兼容
                    self.alias_map[alias.lower()] = steam_id

    def _get_display_name(self, steam_id: str, player_data: dict = None) -> str:
        """获取显示名称：别名 > 游戏昵称 > SteamID"""
        import random
        # 1. Try alias from config
        aliases = self.steam_id_to_aliases.get(str(steam_id), [])
        if aliases:
            return random.choice(aliases)
        
        # 2. Try personaname from player_data
        if player_data and player_data.get('personaname'):
            return player_data['personaname']
            
        # 3. Fallback to Steam ID
        return str(steam_id)

    async def _resolve_steam_id(self, input_id: str) -> str:
        """解析 Steam ID，支持别名 (不区分大小写) 和 Vanity URL"""
        if not input_id:
            return input_id
            
        # 0. Handle URL input (e.g. https://steamcommunity.com/id/de1l3s/)
        # 简单提取逻辑
        if "steamcommunity.com" in input_id:
            input_id = input_id.rstrip("/")
            if "/id/" in input_id:
                input_id = input_id.split("/id/")[-1]
            elif "/profiles/" in input_id:
                input_id = input_id.split("/profiles/")[-1]

        # 1. Check alias (case-insensitive)
        lower_input = input_id.lower()
        if lower_input in self.alias_map:
            return self.alias_map[lower_input]
            
        # 2. Check if it is already a numeric ID
        if input_id.isdigit():
            return input_id
            
        # 3. Try to resolve as Vanity URL
        resolved = await self._resolve_vanity_url(input_id)
        if resolved:
            return resolved
            
        return input_id

    async def _resolve_vanity_url(self, vanity_url: str) -> str:
        if not self.api_key:
            return None
            
        url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
        params = {
            "key": self.api_key,
            "vanityurl": vanity_url
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response = data.get("response", {})
                        if response.get("success") == 1:
                            return response.get("steamid")
            except Exception as e:
                logger.error(f"[Dota2Monitor] Vanity URL resolution failed: {e}")
                
        return None

    def terminate(self):
        """插件卸载/停止时调用"""
        if self.sub_task:
            self.sub_task.cancel()

    async def _subscription_loop(self):
        """订阅循环任务"""
        logger.info("[Dota2Monitor] Subscription task started.")
        tz_shanghai = timezone(timedelta(hours=8))
        
        while True:
            try:
                # 获取 Cron 表达式配置
                # 默认值: 0 0,14,16,18,20,22 * * * (分 时 日 月 周)
                cron_expr = self.config.get("cron_expression", "0 0,14,16,18,20,22 * * *")
                if not cron_expr:
                    cron_expr = "0 0,14,16,18,20,22 * * *"
                
                # 计算下次执行时间 (基于 UTC+8)
                now = datetime.now(tz_shanghai)
                try:
                    iter = croniter(cron_expr, now)
                    next_exec_time = iter.get_next(datetime)
                    wait_seconds = (next_exec_time - now).total_seconds()
                except Exception as e:
                    logger.error(f"[Dota2Monitor] Invalid cron expression: {cron_expr}, error: {e}")
                    # 如果 cron 解析失败，回退到默认 2 小时 (7200秒)
                    wait_seconds = 7200
                
                if wait_seconds < 0:
                    wait_seconds = 60 # 防止负数

                logger.info(f"[Dota2Monitor] Next check at {next_exec_time} (in {wait_seconds:.2f}s)")
                await asyncio.sleep(wait_seconds)
                
                await self._check_subscriptions()
                    
            except asyncio.CancelledError:
                logger.info("[Dota2Monitor] Subscription task cancelled.")
                break
            except Exception as e:
                logger.error(f"[Dota2Monitor] Subscription loop error: {e}")
                await asyncio.sleep(60) # 出错后等待1分钟重试

    async def _check_subscriptions(self):
        """执行一次订阅检查"""
        subscriptions = self.config.get("subscriptions", [])
        groups = self.config.get("groups", [])
        
        if not subscriptions or not groups:
            return 0, []
            
        logger.info(f"[Dota2Monitor] Checking matches for {len(subscriptions)} users...")
        await self._ensure_resources()
        
        # 内存记录最后推送的比赛ID
        if not hasattr(self, "last_pushed_matches"):
            self.last_pushed_matches = {}
            
        # 待推送的比赛: match_id -> {'details': details, 'users': [steam_id]}
        pending_pushes = {}
        
        current_ts = time.time()
        
        for steam_id in subscriptions:
            try:
                # 解析 Steam ID (处理别名、URL等)
                real_steam_id = await self._resolve_steam_id(steam_id)
                if not real_steam_id:
                    logger.warning(f"[Dota2Monitor] Could not resolve Steam ID for subscription: {steam_id}")
                    continue
                    
                monitor = Dota2Monitor(self.api_key, real_steam_id)
                monitor.heroes_map = self.heroes_map
                monitor.items_map = self.items_map
                
                # 获取最近1场比赛
                matches = await monitor.get_recent_matches_details(limit=1)
                if not matches:
                    continue
                    
                match = matches[0]
                match_id = match.get('match_id')
                start_time = match.get('start_time', 0)
                
                last_pushed_id = self.last_pushed_matches.get(real_steam_id)
                
                # 如果是新比赛 (ID不同) 且 发生时间在近期 (比如3小时内)
                # 注意: last_pushed_matches 使用 real_steam_id 作为 key
                if match_id != last_pushed_id:
                    if (current_ts - start_time < 10800):
                        # 更新该用户的最后推送ID
                        self.last_pushed_matches[real_steam_id] = match_id
                        
                        if match_id not in pending_pushes:
                            pending_pushes[match_id] = {
                                'details': match,
                                'users': []
                            }
                        # 这里存 real_steam_id (数字ID) 确保后续 _get_random_alias 能找到配置
                        pending_pushes[match_id]['users'].append(real_steam_id)
                    else:
                        # 比赛太久远，不推送，但也更新 last_pushed_id 以免下次重复检查
                        self.last_pushed_matches[real_steam_id] = match_id
                        logger.debug(f"[Dota2Monitor] Match {match_id} for {real_steam_id} is too old (>3h), skipping push.")
                
            except Exception as e:
                logger.error(f"[Dota2Monitor] Error checking subscription for {steam_id}: {e}")
            
            # 避免触发速率限制
            await asyncio.sleep(2)
            
        # 处理合并推送
        pushed_count = 0
        failed_pushes = []
        
        for match_id, data in pending_pushes.items():
            details = data['details']
            involved_users = data['users'] # list of real_steam_ids
            
            # 为每个参与的用户生成战报
            # 需要在 details['players'] 中找到对应的数据
            monitor_helper = Dota2Monitor(self.api_key) # 用于调用工具方法
            
            user_player_data_map = {}
            for uid in involved_users:
                try:
                    account_id_32 = monitor_helper.convert_to_32bit(uid)
                    for p in details.get('players', []):
                        if p.get('account_id') == account_id_32:
                            user_player_data_map[uid] = p
                            break
                except:
                    pass
            
            # 构造合并消息文本
            # [别名1], [别名2] 刚刚完成了一场比赛
            display_names = []
            for uid in involved_users:
                player_data = user_player_data_map.get(uid)
                display_names.append(self._get_display_name(uid, player_data))
                
            header = f"{', '.join(display_names)} 刚刚完成了一场比赛。"
            
            user_reports = []
            
            for uid in involved_users:
                player_data = user_player_data_map.get(uid)
                if player_data:
                    name = self._get_display_name(uid, player_data)
                    hero = player_data.get('hero_name', 'Unknown')
                    
                    # 判断输赢
                    is_radiant = player_data.get('team') == 'Radiant'
                    radiant_win = details.get('radiant_win')
                    result = "胜利" if (is_radiant == radiant_win) else "失败"
                    
                    kda = player_data.get('kda', '0/0/0')
                    
                    # 评价
                    eval_text = monitor_helper.evaluate_performance(player_data)
                    
                    user_reports.append(f"{name} 使用 {hero} ({result})，KDA: {kda}，{eval_text}")
            
            full_text = header + "\n" + "\n".join(user_reports)
            
            logger.info(f"[Dota2Monitor] Pushing match {match_id} for users {involved_users}")
            success, errors = await self._push_match_image(details, groups, text_msg=full_text)
            if success:
                pushed_count += 1
            else:
                failed_pushes.extend(errors)
            
        return pushed_count, failed_pushes

    @command("dota2_check_sub")
    async def check_subscription(self, event: AstrMessageEvent):
        """手动触发一次订阅检查"""
        yield event.plain_result("开始手动检查订阅更新...")
        count, errors = await self._check_subscriptions()
        if errors:
            yield event.plain_result(f"检查完成，推送了 {count} 场新比赛。但出现以下错误：\n" + "\n".join(errors))
        else:
            yield event.plain_result(f"检查完成，推送了 {count} 场新比赛。")

    async def _push_match_image(self, details, groups, text_msg=None):
        errors = []
        try:
            # 渲染图片
            img_bytes = await self.renderer.render(details)
            
            temp_dir = os.path.join(os.path.dirname(__file__), "temp")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            match_id = details.get('match_id', 'unknown')
            temp_path = os.path.join(temp_dir, f"sub_{match_id}.jpg")
            with open(temp_path, "wb") as f:
                f.write(img_bytes)
                
            # 发送消息给所有群组
            success_count = 0
            
            # 1. 先发送文字 (如果有)
            if text_msg:
                logger.info(f"[Dota2Monitor] Preparing to send text message ({len(text_msg)} chars) for match {match_id}")
                text_chain = MessageChain().message(text_msg)
                
                for group_id in groups:
                    try:
                        logger.debug(f"[Dota2Monitor] Sending text to {group_id}")
                        await self.context.send_message(group_id, text_chain)
                    except Exception as e:
                        err_msg = f"Failed to send text to group {group_id}: {e}"
                        logger.error(f"[Dota2Monitor] {err_msg}")
                        errors.append(err_msg)

            # 2. 再发送图片
            logger.info(f"[Dota2Monitor] Preparing to send image for match {match_id}")
            img_chain = MessageChain()
            img_chain.chain.append(Image.fromFileSystem(temp_path))
            
            for group_id in groups:
                try:
                    logger.debug(f"[Dota2Monitor] Sending image to {group_id}")
                    await self.context.send_message(group_id, img_chain)
                    success_count += 1
                except Exception as e:
                    err_msg = f"Failed to send image to group {group_id}: {e}"
                    logger.error(f"[Dota2Monitor] {err_msg}")
                    errors.append(err_msg)
            
            return success_count > 0, errors

        except Exception as e:
            err_msg = f"Failed to push match image: {e}"
            logger.error(f"[Dota2Monitor] {err_msg}")
            errors.append(err_msg)
            return False, errors

    @command("dota2_bind")
    async def bind_notify(self, event: AstrMessageEvent):
        """绑定当前会话为比赛推送目标"""
        if not event.unified_msg_origin:
            yield event.plain_result("无法获取当前会话的唯一标识符。")
            return
            
        group_id = event.unified_msg_origin
        groups = self.config.get("groups", [])
        
        if group_id not in groups:
            groups.append(group_id)
            self.config["groups"] = groups
            yield event.plain_result(f"绑定成功！当前群组 ({group_id}) 已添加到推送列表。")
        else:
            yield event.plain_result(f"当前群组 ({group_id}) 已经在推送列表中了。")

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
            yield event.plain_result(f"图片生成失败: {e}")

    @command("dota2_debug")
    async def debug_mc(self, event: AstrMessageEvent):
        chain = MessageChain()
        logger.info(f"MessageChain dir: {dir(chain)}")
        try:
            logger.info(f"MessageChain vars: {vars(chain)}")
        except:
            pass
        yield event.plain_result("Debug info logged.")

    @command("dota2_recent")
    async def query_recent(self, event: AstrMessageEvent, steam_id: str, limit: int = None):
        """查询用户最近比赛。格式: /dota2_recent <SteamID/别名> [数量]"""
        if not self.api_key:
            yield event.plain_result("请先在插件配置中设置 Steam API Key。")
            return

        if not steam_id:
            yield event.plain_result("请提供 Steam 64位 ID 或已配置的别名。")
            return
            
        # 处理数量参数
        max_limit = self.config.get("max_recent_matches", 5)
        if not limit:
            limit = max_limit
        else:
            if limit > max_limit:
                limit = max_limit
            if limit <= 0:
                limit = max_limit
            
        # 解析别名
        real_steam_id = await self._resolve_steam_id(steam_id)

        await self._ensure_resources()
        
        yield event.plain_result(f"正在查询用户 {real_steam_id} 的最近 {limit} 场比赛，请稍候...")
        
        monitor = Dota2Monitor(self.api_key, real_steam_id)
        monitor.heroes_map = self.heroes_map
        monitor.items_map = self.items_map
        
        # 获取详细数据列表
        matches_details = await monitor.get_recent_matches_details(limit=limit)
        
        if not matches_details:
            yield event.plain_result("未找到比赛记录。")
            return
            
        # 1. 生成总结文本
        wins = 0
        losses = 0
        
        target_account_id = monitor.steam_id_32
        target_player_data = None
        
        for details in matches_details:
            # 查找目标玩家
            player = next((p for p in details.get('players', []) if p.get('account_id') == target_account_id), None)
            
            if player:
                if not target_player_data:
                    target_player_data = player
                    
                is_radiant = player.get('team') == 'Radiant'
                radiant_win = details.get('radiant_win')
                # 胜利条件: (是天辉且天辉赢) 或 (是夜魇且天辉输) -> (is_radiant == radiant_win)
                if is_radiant == radiant_win:
                    wins += 1
                else:
                    losses += 1
        
        total = wins + losses
        win_rate = (wins / total) if total > 0 else 0
        
        # 描述语
        if win_rate >= 0.8:
            desc = "恭喜恭喜最近上了大分！"
        elif win_rate >= 0.6:
            desc = "状态火热，切勿骄傲！"
        elif win_rate >= 0.4:
            desc = "有输有赢，平平淡淡才是真。"
        elif win_rate >= 0.2:
            desc = "逆风局有点多，调整心态。"
        else:
            desc = "这也太惨了，建议休息一下（或者找个大腿）。"
            
        alias = self._get_display_name(real_steam_id, target_player_data)
        summary = f"{alias} 刚刚完成了 {total} 场比赛，{wins} 胜 {losses} 负，{desc}"
        yield event.plain_result(summary)

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
                chain = MessageChain()
                chain.chain.append(Image.fromFileSystem(temp_path))
                yield event.chain_result(chain)
                
            except Exception as e:
                yield event.plain_result(f"比赛 {details.get('match_id')} 图片生成失败: {e}")
