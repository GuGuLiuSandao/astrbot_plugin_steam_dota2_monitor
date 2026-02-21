import aiohttp
import asyncio
import json
import time
import datetime

# API 端点
API_BASE = "https://api.steampowered.com"
OPENDOTA_API_BASE = "https://api.opendota.com/api"
# Valve CDN for images (avoids OpenDota rate limits)
VALVE_CDN_BASE = "https://cdn.cloudflare.steamstatic.com"

class Dota2Monitor:
    def __init__(self, api_key, steam_id=None):
        self.api_key = api_key
        self.steam_id_64 = steam_id  # 64位ID (用于 Steam API)
        self.steam_id_32 = self.convert_to_32bit(steam_id) if steam_id else None # 32位ID (用于 Dota2 API)
        self.heroes_map = {}
        self.items_map = {}

    def convert_to_32bit(self, steam_id_64):
        """将64位 Steam ID 转换为 32位 Account ID"""
        return int(steam_id_64) - 76561197960265728

    def convert_to_64bit(self, steam_id_32):
        """将32位 Account ID 转换为 64位 Steam ID"""
        return int(steam_id_32) + 76561197960265728

    async def get_player_summaries(self, steam_ids_64):
        """批量获取玩家摘要信息 (头像、昵称)"""
        if not steam_ids_64:
            return {}
            
        # 每次最多查询 100 个 ID
        ids_str = ",".join(map(str, steam_ids_64))
        url = f"{API_BASE}/ISteamUser/GetPlayerSummaries/v0002/"
        params = {
            "key": self.api_key,
            "steamids": ids_str
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        players = data.get('response', {}).get('players', [])
                        # 返回 map: steam_id_64 -> {personaname}
                        result = {}
                        for p in players:
                            sid = p.get('steamid')
                            result[sid] = {
                                'personaname': p.get('personaname')
                            }
                        return result
                    else:
                        return {}
            except Exception as e:
                return {}

    async def load_heroes(self):
        """从 OpenDota 和 Steam API 获取英雄数据并建立映射"""
        if self.heroes_map:
            return
            
        temp_heroes = {} # id -> {img, name}
        
        async with aiohttp.ClientSession() as session:
            # 1. 获取 OpenDota 英雄数据 (用于图片)
            try:
                async with session.get(f"{OPENDOTA_API_BASE}/heroes") as resp:
                    if resp.status == 200:
                        heroes = await resp.json()
                        for h in heroes:
                            temp_heroes[h['id']] = {
                                'name': h['localized_name'], # 默认英文名
                                'img': f"{VALVE_CDN_BASE}{h['img']}"
                            }
            except Exception as e:
                pass

            # 2. 获取 Steam 英雄数据 (用于中文名)
            if self.api_key:
                try:
                    url = f"{API_BASE}/IEconDOTA2_570/GetHeroes/v1/"
                    params = {"key": self.api_key, "language": "zh"}
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'result' in data and 'heroes' in data['result']:
                                for h in data['result']['heroes']:
                                    hid = h['id']
                                    if hid in temp_heroes:
                                        temp_heroes[hid]['name'] = h['localized_name']
                                    else:
                                        # 如果 OpenDota 没返回这个英雄 (不太可能)，则只有名字
                                        name_suffix = h['name'].replace('npc_dota_hero_', '')
                                        temp_heroes[hid] = {
                                            'name': h['localized_name'],
                                            'img': f"{VALVE_CDN_BASE}/apps/dota2/images/heroes/{name_suffix}_full.png"
                                        }
                except Exception as e:
                    pass
        
        self.heroes_map = temp_heroes

    async def load_items(self):
        """从 OpenDota 和 Steam API 获取物品数据并建立映射"""
        if self.items_map:
            return

        temp_items = {} # id -> {img, name}

        async with aiohttp.ClientSession() as session:
            # 1. 获取 OpenDota 物品数据 (用于图片)
            try:
                async with session.get(f"{OPENDOTA_API_BASE}/constants/items") as resp:
                    if resp.status == 200:
                        items = await resp.json()
                        for key, data in items.items():
                            if data and 'id' in data:
                                temp_items[data['id']] = {
                                    'name': data.get('dname', key), # 默认英文名
                                    'img': f"{VALVE_CDN_BASE}{data['img']}"
                                }
            except Exception as e:
                pass

            # 2. 获取 Steam 物品数据 (用于中文名)
            if self.api_key:
                try:
                    url = f"{API_BASE}/IEconDOTA2_570/GetGameItems/v1/"
                    params = {"key": self.api_key, "language": "zh"}
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'result' in data and 'items' in data['result']:
                                for item in data['result']['items']:
                                    iid = item['id']
                                    if iid in temp_items:
                                        temp_items[iid]['name'] = item['localized_name']
                except Exception as e:
                    pass
        
        self.items_map = temp_items

    async def enrich_player_names(self, details):
        """补全玩家昵称"""
        steam_ids = []
        for p in details.get('players', []):
            if p.get('account_id') and p.get('account_id') != 4294967295:
                steam_ids.append(self.convert_to_64bit(p['account_id']))
        
        summaries = await self.get_player_summaries(steam_ids)
        
        for p in details.get('players', []):
            if p.get('account_id'):
                sid64 = str(self.convert_to_64bit(p['account_id']))
                if sid64 in summaries:
                    p['personaname'] = summaries[sid64].get('personaname')
        return details

    async def get_enriched_match_details(self, match_id):
        """获取包含玩家昵称的比赛详情"""
        async with aiohttp.ClientSession() as session:
            details = await self.get_match_details(match_id, session)
            if details:
                return await self.enrich_player_names(details)
            return None

    async def get_recent_matches_details(self, limit=5):
        """获取最近比赛的详细数据列表"""
        if not self.steam_id_64:
            return []
            
        matches_data = []
        
        async with aiohttp.ClientSession() as session:
            # 尝试 1: Steam API
            url = f"{API_BASE}/IDOTA2Match_570/GetMatchHistory/v1/"
            params = {
                "key": self.api_key,
                "account_id": self.steam_id_64,
                "matches_requested": limit
            }
            
            matches = []
            
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if 'result' in data and 'matches' in data['result']:
                            matches = data['result']['matches']
            except Exception:
                pass

            # Fallback to OpenDota
            if not matches:
                opendota_url = f"{OPENDOTA_API_BASE}/players/{self.steam_id_32}/matches"
                opendota_params = {"limit": limit}
                try:
                    async with session.get(opendota_url, params=opendota_params) as resp:
                        if resp.status == 200:
                            matches = await resp.json()
                except Exception as e:
                    print(f"Error fetching matches from OpenDota: {e}")

            if not matches:
                return []

            for m in matches:
                match_id = m.get('match_id')
                if not match_id:
                    continue
                
                # 获取详情
                details = await self.get_match_details(match_id, session)
                if details:
                    # 丰富玩家信息
                    steam_ids = []
                    for p in details.get('players', []):
                        if p.get('account_id') and p.get('account_id') != 4294967295:
                            steam_ids.append(self.convert_to_64bit(p['account_id']))
                    
                    summaries = await self.get_player_summaries(steam_ids)
                    
                    for p in details.get('players', []):
                        if p.get('account_id'):
                            sid64 = str(self.convert_to_64bit(p['account_id']))
                            if sid64 in summaries:
                                p['personaname'] = summaries[sid64].get('personaname')
                    
                    matches_data.append(details)
                
                # 避免触发速率限制
                await asyncio.sleep(0.5)
                
        return matches_data

    async def get_recent_matches_str(self):
        """获取最近比赛并返回格式化字符串"""
        if not self.steam_id_64:
            return "未设置 Steam ID，无法查询最近比赛。"
            
        output = []
        # output.append(f"正在查询用户 {self.steam_id_64} 的最近5场比赛...")
        
        async with aiohttp.ClientSession() as session:
            # 尝试 1: Steam API
            url = f"{API_BASE}/IDOTA2Match_570/GetMatchHistory/v1/"
            params = {
                "key": self.api_key,
                "account_id": self.steam_id_64,
                "matches_requested": 5
            }
            
            matches = []
            source = "Steam API"
            
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if 'result' in data and 'matches' in data['result']:
                            matches = data['result']['matches']
                    else:
                        source = "OpenDota API"
            except Exception:
                source = "OpenDota API"

            # Fallback to OpenDota
            if not matches:
                opendota_url = f"{OPENDOTA_API_BASE}/players/{self.steam_id_32}/matches"
                opendota_params = {"limit": 5}
                try:
                    async with session.get(opendota_url, params=opendota_params) as resp:
                        if resp.status == 200:
                            matches = await resp.json()
                            source = "OpenDota API"
                except Exception as e:
                    return f"查询失败: {e}"

            if not matches:
                return "未找到比赛记录。"

            output.append(f"数据来源: {source}")
            
            for m in matches:
                match_id = m.get('match_id')
                if not match_id:
                    continue
                details = await self.get_match_details(match_id, session)
                if details:
                    # 尝试获取玩家头像 (如果 Steam Key 有效)
                    steam_ids = []
                    for p in details.get('players', []):
                        if p.get('account_id') and p.get('account_id') != 4294967295:
                            steam_ids.append(self.convert_to_64bit(p['account_id']))
                    
                    summaries = await self.get_player_summaries(steam_ids)
                    
                    for p in details.get('players', []):
                        if p.get('account_id'):
                            sid64 = str(self.convert_to_64bit(p['account_id']))
                            if sid64 in summaries:
                                p['personaname'] = summaries[sid64].get('personaname')

                    output.append(self.format_match_details(details))
                await asyncio.sleep(0.5)
                
        return "\n".join(output)

    async def get_match_details_str(self, match_id):
        """获取单场比赛详情字符串"""
        async with aiohttp.ClientSession() as session:
            details = await self.get_match_details(match_id, session)
            if details:
                # 尝试获取玩家头像 (如果 Steam Key 有效)
                steam_ids = []
                for p in details.get('players', []):
                    if p.get('account_id') and p.get('account_id') != 4294967295:
                        steam_ids.append(self.convert_to_64bit(p['account_id']))
                
                summaries = await self.get_player_summaries(steam_ids)
                
                for p in details.get('players', []):
                    if p.get('account_id'):
                        sid64 = str(self.convert_to_64bit(p['account_id']))
                        if sid64 in summaries:
                            p['personaname'] = summaries[sid64].get('personaname')
                            
                return self.format_match_details(details)
            else:
                return f"无法获取比赛 {match_id} 的详情。"

    async def get_match_details(self, match_id, session):
        """获取单场比赛详细信息 (优先尝试 Steam API，失败则尝试 OpenDota API)"""
        # 尝试 1: Steam API
        url = f"{API_BASE}/IDOTA2Match_570/GetMatchDetails/v1/"
        params = {
            "key": self.api_key,
            "match_id": match_id
        }
        
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'result' in data:
                        return self.parse_match_data(data['result'])
        except Exception:
            pass

        # 尝试 2: OpenDota API
        opendota_url = f"{OPENDOTA_API_BASE}/matches/{match_id}"
        try:
            async with session.get(opendota_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self.parse_match_data(data)
        except Exception:
            pass
            
        return None

    def parse_match_data(self, match_data):
        """解析单场比赛数据"""
        # 1. 基础信息
        match_id = match_data.get('match_id')
        start_time = match_data.get('start_time', 0)
        duration = match_data.get('duration', 0)
        radiant_win = match_data.get('radiant_win')
        
        # 格式化时间
        dt_object = datetime.datetime.fromtimestamp(start_time)
        time_str = dt_object.strftime("%Y-%m-%d %H:%M:%S")
        
        # 格式化时长
        m, s = divmod(duration, 60)
        duration_str = f"{m}分{s}秒"

        # 2. 详细玩家数据提取
        players_details = []
        target_player_info = None

        for p in match_data.get('players', []):
            # 获取英雄名称
            hero_id = p.get('hero_id')
            hero_data = self.heroes_map.get(hero_id, {})
            hero_name = hero_data.get('name', f"Unknown Hero ({hero_id})")
            hero_img = hero_data.get('img', "")
            
            # 基础数据
            kills = p.get('kills', 0)
            deaths = p.get('deaths', 0)
            assists = p.get('assists', 0)
            kda = f"{kills}/{deaths}/{assists}"
            
            # 进阶数据
            last_hits = p.get('last_hits', 0)
            denies = p.get('denies', 0)
            lh_dn = f"{last_hits}/{denies}"
            
            gold_per_min = p.get('gold_per_min', 0)
            xp_per_min = p.get('xp_per_min', 0)
            gpm_xpm = f"{gold_per_min}/{xp_per_min}"
            
            hero_damage = p.get('hero_damage', 0)
            tower_damage = p.get('tower_damage', 0)
            hd_td = f"{hero_damage // 1000}k/{tower_damage}" if hero_damage >= 1000 else f"{hero_damage}/{tower_damage}"
            
            # 物品 (item_0 ~ item_5) + item_neutral + backpack (item_0 ~ item_2)
            # 注意: Steam API 返回的 backpack 是 item_backpack_0 ~ item_backpack_2
            # OpenDota API 返回的 backpack_0 ~ backpack_2
            items_str_list = []
            item_imgs = []
            
            # 主物品栏 0-5
            for i in range(6):
                item_id = p.get(f'item_{i}')
                if item_id:
                    item_data = self.items_map.get(item_id, {})
                    item_name = item_data.get('name', str(item_id))
                    item_img = item_data.get('img', "")
                    items_str_list.append(item_name)
                    item_imgs.append(item_img)
                else:
                    item_imgs.append("") # 占位
            
            # 背包物品 (尝试两种字段名)
            backpack_imgs = []
            for i in range(3):
                item_id = p.get(f'backpack_{i}') or p.get(f'item_backpack_{i}')
                if item_id:
                    item_data = self.items_map.get(item_id, {})
                    item_img = item_data.get('img', "")
                    backpack_imgs.append(item_img)
                else:
                    backpack_imgs.append("")

            # 中立物品
            neutral_item_id = p.get('item_neutral')
            if neutral_item_id:
                n_data = self.items_map.get(neutral_item_id, {})
                n_name = n_data.get('name', str(neutral_item_id))
                n_img = n_data.get('img', "")
                items_str_list.append(f"({n_name})")
                item_imgs.append(n_img)
            else:
                item_imgs.append("")

            items_str = ", ".join(items_str_list) if items_str_list else "-"

            # Net Worth
            gold = p.get('gold', 0)
            gold_spent = p.get('gold_spent', 0)
            net_worth = gold + gold_spent
            nw_str = f"{net_worth / 1000:.1f}K" if net_worth >= 1000 else str(net_worth)

            # 获取玩家名称 (OpenDota fallback)
            personaname = p.get('personaname', 'Anonymous')
            if not personaname:
                 personaname = 'Anonymous'

            player_info = {
                'player_slot': p.get('player_slot'),
                'account_id': p.get('account_id'), # 32位ID
                'personaname': personaname, # 玩家昵称
                'hero_id': hero_id,
                'hero_name': hero_name,
                'hero_img': hero_img,
                'level': p.get('level', 0),
                'kda': kda,
                'kills': kills,
                'deaths': deaths,
                'assists': assists,
                'lh_dn': lh_dn,
                'gpm_xpm': gpm_xpm,
                'gpm': gold_per_min,
                'xpm': xp_per_min,
                'hd_td': hd_td,
                'damage': f"{hero_damage / 1000:.1f}K" if hero_damage >= 1000 else str(hero_damage),
                'items': items_str,
                'item_imgs': item_imgs,
                'backpack_imgs': backpack_imgs,
                'net_worth': nw_str,
                'team': 'Radiant' if p.get('player_slot', 0) < 128 else 'Dire'
            }
            players_details.append(player_info)

            # 检查是否是目标玩家
            if self.steam_id_32 and p.get('account_id') == self.steam_id_32:
                target_player_info = player_info
                # 判断输赢
                is_radiant = p.get('player_slot', 0) < 128
                if (radiant_win and is_radiant) or (not radiant_win and not is_radiant):
                    target_player_info['result'] = "胜利"
                else:
                    target_player_info['result'] = "失败"

        return {
            'match_id': match_id,
            'time_str': time_str,
            'duration_str': duration_str,
            'radiant_win': radiant_win,
            'players': players_details,
            'target_player': target_player_info
        }

    def format_match_details(self, details):
        """格式化比赛详情为字符串"""
        if not details:
            return "无法获取比赛详情"
            
        lines = []
        match_id = details.get('match_id')
        dt = details.get('time_str', 'Unknown')
        duration_str = details.get('duration_str', 'Unknown')
        
        lines.append("=" * 80)
        lines.append(f"比赛ID: {match_id} | 时间: {dt} | 时长: {duration_str}")
        
        # 查找请求玩家的数据 (如果有)
        if details.get('target_player'):
            tp = details['target_player']
            lines.append(f"你的表现: {tp['hero_name']} ({tp['result']}) | KDA: {tp['kda']}")
        
        lines.append("-" * 80)
        header = f"{'英雄':<15} | {'玩家':<15} | {'K/D/A':<10} | {'LH/DN':<10} | {'GPM/XPM':<10} | {'HD/TD':<12} | {'物品'}"
        lines.append(header)
        lines.append("-" * 80)
        
        # 分队处理
        radiant = []
        dire = []
        
        for p in details['players']:
            hero_name = p.get('hero_name', 'Unknown')
            personaname = p.get('personaname', 'Anonymous')
            kda = p.get('kda', '0/0/0')
            lh_dn = p.get('lh_dn', '0/0')
            gpm_xpm = p.get('gpm_xpm', '0/0')
            hd_td = p.get('hd_td', '0/0')
            items_str = p.get('items', '')
            
            # 截断长名字
            h_name = (hero_name[:13] + '..') if len(hero_name) > 13 else hero_name
            p_name = (personaname[:13] + '..') if len(personaname) > 13 else personaname
            
            # 标记目标玩家
            marker = "*" if self.steam_id_32 and p.get('account_id') == self.steam_id_32 else " "
            
            row = f"{marker}{h_name:<14} | {p_name:<15} | {kda:<10} | {lh_dn:<10} | {gpm_xpm:<10} | {hd_td:<12} | {items_str}"
            
            if p.get('team') == 'Radiant':
                radiant.append(row)
            else:
                dire.append(row)

        lines.append(f"天辉 ({'胜利' if details.get('radiant_win') else '失败'})")
        lines.extend(radiant)
        lines.append("-" * 80)
        lines.append(f"夜魇 ({'失败' if details.get('radiant_win') else '胜利'})")
        lines.extend(dire)
        lines.append("=" * 80)
        
        return "\n".join(lines)
