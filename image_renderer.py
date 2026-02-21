
import os
import asyncio
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

class MatchRenderer:
    def __init__(self, resources_dir):
        self.resources_dir = resources_dir
        if not os.path.exists(resources_dir):
            os.makedirs(resources_dir)
            
        self.images_cache_dir = os.path.join(resources_dir, "images")
        if not os.path.exists(self.images_cache_dir):
            os.makedirs(self.images_cache_dir)

        # 尝试加载字体
        self.font_path = self._find_font()
        self.font_size_large = 32
        self.font_size_medium = 20
        self.font_size_small = 16
        
    def _find_font(self):
        # 1. 优先使用本插件 resources 目录下的字体
        local_font_dir = os.path.join(self.resources_dir, "fonts")
        if not os.path.exists(local_font_dir):
            os.makedirs(local_font_dir, exist_ok=True)
            
        for f in os.listdir(local_font_dir):
            if f.endswith(('.ttf', '.otf', '.ttc')):
                path = os.path.join(local_font_dir, f)
                print(f"[Dota2Monitor] Using local font: {path}")
                return path

        # 2. 尝试使用 steam_status_monitor 插件的字体
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上两级找到 plugins 目录 (assuming standard AstrBot structure)
        # astrbot_plugin_steam_dota2_monitor -> plugins -> astrbot_plugin_steam_status_monitor
        parent_dir = os.path.dirname(current_dir) 
        
        # 尝试多个可能的路径
        possible_paths = [
            os.path.join(parent_dir, "astrbot_plugin_steam_status_monitor", "fonts", "NotoSansHans-Regular.otf"),
            os.path.join(parent_dir, "steam_status_monitor", "fonts", "NotoSansHans-Regular.otf"), # 可能是这个名字
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"[Dota2Monitor] Using font from: {path}")
                return path
            
        # 备选字体
        candidates = [
            "/System/Library/Fonts/PingFang.ttc", # macOS
            "/System/Library/Fonts/STHeiti Light.ttc",
            "C:/Windows/Fonts/msyh.ttc", # Windows
            "C:/Windows/Fonts/simhei.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", # Linux
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ]
        for path in candidates:
            if os.path.exists(path):
                print(f"[Dota2Monitor] Using system font: {path}")
                return path
                
        print("[Dota2Monitor] No suitable font found, text may be garbled.")
        return None 

    async def _download_image(self, session, url, filename):
        if not url:
            return None
            
        # 确保文件名合法
        safe_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in ('-', '_', '.')])
        
        # 1. 检查 resources 目录 (预下载的资源)
        # 尝试在 heroes 和 items 目录下查找
        resource_hero_path = os.path.join(self.resources_dir, "images", "heroes", safe_filename)
        if os.path.exists(resource_hero_path):
            return resource_hero_path
            
        resource_item_path = os.path.join(self.resources_dir, "images", "items", safe_filename)
        if os.path.exists(resource_item_path):
            return resource_item_path

        # 2. 检查缓存目录
        path = os.path.join(self.images_cache_dir, safe_filename)
        if os.path.exists(path):
            return path
        
        # 3. 下载
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
                else:
                    print(f"[Dota2Monitor] Failed to download {url}: Status {resp.status}")
        except Exception as e:
            print(f"[Dota2Monitor] Failed to download {url}: {e}")
            pass
        return None

    def _get_font(self, size):
        if self.font_path:
            try:
                return ImageFont.truetype(self.font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    async def render(self, details):
        # 1. 准备画布
        width = 1400 # 增加宽度以容纳所有内容
        # Header: 100
        # Team Header + Column Header: 80 (was 50)
        # Players: 5 * 70 = 350
        # Footer: 30
        height = 100 + 80 + 350 + 30
        
        img = Image.new('RGB', (width, height), color='#1b1b1b') # 深色背景
        draw = ImageDraw.Draw(img)
        
        font_large = self._get_font(self.font_size_large)
        font_medium = self._get_font(self.font_size_medium)
        font_small = self._get_font(self.font_size_small)
        
        # 2. 绘制头部
        match_id = details.get('match_id', 'Unknown')
        title = f"Dota 2 比赛详情 {match_id}"
        
        # 居中绘制标题
        # 使用 textbbox 计算文字宽度 (Pillow >= 9.2.0)
        # 兼容旧版本
        try:
            w = draw.textlength(title, font=font_large)
            draw.text(((width - w) / 2, 30), title, font=font_large, fill='white')
        except:
            draw.text((width//2, 30), title, font=font_large, fill='white', anchor="mm")

        # 副标题
        time_str = details.get('time_str', 'Unknown')
        duration_str = details.get('duration_str', 'Unknown')
        subtitle = f"{time_str} | 持续时间: {duration_str}"
        
        try:
            w = draw.textlength(subtitle, font=font_small)
            draw.text(((width - w) / 2, 70), subtitle, font=font_small, fill='#888888')
        except:
            draw.text((width//2, 70), subtitle, font=font_small, fill='#888888', anchor="mm")
        
        # 3. 准备资源下载
        url_map = {}
        async with aiohttp.ClientSession() as session:
            tasks = []
            # 收集 URLs
            for p in details.get('players', []):
                # Hero
                if p.get('hero_img'):
                    hero_url = p.get('hero_img')
                    hero_fname = os.path.basename(hero_url.split('?')[0])
                    tasks.append(self._download_image(session, hero_url, hero_fname))
                
                # Items
                for i, item_url in enumerate(p.get('item_imgs', [])):
                    if item_url:
                        item_fname = os.path.basename(item_url.split('?')[0])
                        tasks.append(self._download_image(session, item_url, item_fname))
            
            # 并发下载
            results = await asyncio.gather(*tasks)
            
            # 建立映射
            for p in details.get('players', []):
                if p.get('hero_img'):
                    hero_url = p.get('hero_img')
                    # 尝试从 resources 或 cache 加载
                    fname = os.path.basename(hero_url.split('?')[0])
                    
                    # 优先检查 resources
                    safe_filename = "".join([c for c in fname if c.isalpha() or c.isdigit() or c in ('-', '_', '.')])
                    resource_path = os.path.join(self.resources_dir, "images", "heroes", safe_filename)
                    if os.path.exists(resource_path):
                        url_map[hero_url] = resource_path
                    else:
                        cache_path = os.path.join(self.images_cache_dir, safe_filename)
                        if os.path.exists(cache_path):
                            url_map[hero_url] = cache_path
                
                for item_url in p.get('item_imgs', []):
                    if item_url:
                        fname = os.path.basename(item_url.split('?')[0])
                        safe_filename = "".join([c for c in fname if c.isalpha() or c.isdigit() or c in ('-', '_', '.')])
                        
                        resource_path = os.path.join(self.resources_dir, "images", "items", safe_filename)
                        if os.path.exists(resource_path):
                            url_map[item_url] = resource_path
                        else:
                            cache_path = os.path.join(self.images_cache_dir, safe_filename)
                            if os.path.exists(cache_path):
                                url_map[item_url] = cache_path

        # 4. 绘制队伍
        col_width = (width - 60) // 2
        start_y = 110
        
        # 天辉 (左)
        self._draw_team(img, draw, details, 'Radiant', 20, start_y, col_width, url_map, font_medium, font_small)
        
        # 夜魇 (右)
        self._draw_team(img, draw, details, 'Dire', 20 + col_width + 20, start_y, col_width, url_map, font_medium, font_small)

        # 5. 返回图片字节
        output = BytesIO()
        img.save(output, format='JPEG', quality=90)
        return output.getvalue()

    def _draw_team(self, img, draw, details, team_name, start_x, start_y, width, url_map, font_medium, font_small):
        radiant_win = details.get('radiant_win')
        is_radiant = team_name == 'Radiant'
        is_win = (is_radiant and radiant_win) or (not is_radiant and not radiant_win)
        
        # 队伍颜色
        team_color = '#2E7D32' if is_radiant else '#C62828' # Green / Red
        
        # 绘制 Header 背景
        draw.rectangle([start_x, start_y, start_x + width, start_y + 40], fill=team_color)
        
        header_text = f"{'天辉' if is_radiant else '夜魇'} - {'胜利' if is_win else '失败'}"
        draw.text((start_x + 20, start_y + 8), header_text, font=font_medium, fill='white')
        
        # 表头 (Added Headers)
        header_y = start_y + 45
        
        # Coordinates used in loop later, define here or reuse logic
        h_hero_x = start_x + 10
        h_info_x = h_hero_x + 70
        h_stats_x = h_info_x + 160
        h_gpm_x = h_stats_x + 100
        h_items_x = h_stats_x + 180
        
        draw.text((h_hero_x, header_y), "英雄", font=font_small, fill='#888888')
        draw.text((h_info_x, header_y), "玩家", font=font_small, fill='#888888')
        draw.text((h_stats_x, header_y), "K/D/A | 经济", font=font_small, fill='#888888')
        draw.text((h_gpm_x, header_y), "英雄伤害", font=font_small, fill='#888888')
        draw.text((h_items_x, header_y), "物品", font=font_small, fill='#888888')

        # 玩家列表
        players = [p for p in details.get('players', []) if p.get('team') == team_name]
        
        row_h = 70
        current_y = start_y + 70 # Shifted down to accommodate headers
        
        for idx, p in enumerate(players):
            # 斑马纹背景
            bg_color = '#252526' if idx % 2 == 0 else '#1e1e1e'
            draw.rectangle([start_x, current_y, start_x + width, current_y + row_h], fill=bg_color)
            
            # 1. 英雄图片 (60x34)
            hero_url = p.get('hero_img')
            hero_x = start_x + 10
            hero_y = current_y + 12 # 略微上移 (原18)
            
            if hero_url and hero_url in url_map:
                try:
                    hero_img = Image.open(url_map[hero_url]).convert("RGBA")
                    hero_img = hero_img.resize((60, 34), Image.Resampling.LANCZOS)
                    img.paste(hero_img, (hero_x, hero_y), hero_img)
                except:
                    draw.rectangle([hero_x, hero_y, hero_x + 60, hero_y + 34], fill='#444')
            else:
                draw.rectangle([hero_x, hero_y, hero_x + 60, hero_y + 34], fill='#444')
                
            # 等级 (移到头像下方)
            # anchor="mm" 表示以坐标为中心
            # y坐标: hero_y (12) + height (34) + padding (10) = 56
            draw.text((hero_x + 30, hero_y + 34 + 8), f"Lv.{p.get('level')}", font=font_small, fill='#cccccc', anchor="mm")

            # 2. 玩家信息
            info_x = hero_x + 70
            p_name = p.get('personaname', 'Unknown')
            h_name = p.get('hero_name', 'Unknown')
            
            # 截断
            if len(p_name) > 12: p_name = p_name[:12] + ".."
            
            draw.text((info_x, current_y + 12), p_name, font=font_medium, fill='#eeeeee')
            draw.text((info_x, current_y + 38), h_name, font=font_small, fill='#999999')
            
            # 3. KDA & Net Worth
            # 布局: KDA | NW
            stats_x = info_x + 160
            
            kda = p.get('kda', '0/0/0')
            nw = p.get('net_worth', '0')
            
            draw.text((stats_x, current_y + 12), kda, font=font_medium, fill='white')
            draw.text((stats_x, current_y + 38), f"经济: {nw}", font=font_small, fill='#FFD700') # Gold color
            
            # 4. 伤害 (Hero Damage)
            # damage 格式如 "32.1K" or "500"
            dmg = p.get('damage', '0')
            draw.text((stats_x + 100, current_y + 25), dmg, font=font_small, fill='#FF5722') # Orange/Red for damage
            
            # 5. 物品栏 (3x3 grid: 6 items + 3 backpack items)
            # item_imgs 包含 7 个元素 (6 items + 1 neutral)
            # 我们需要把 neutral 分开处理，把 6 个物品放上面两行
            # 还需要获取背包物品 (3个) 放第三行
            items_x = stats_x + 180
            
            main_items = p.get('item_imgs', [])[:6] # 前6个是主物品
            neutral_item = p.get('item_imgs', [])[6] if len(p.get('item_imgs', [])) > 6 else ""
            backpack_items = p.get('backpack_imgs', []) # 背包物品

            item_size = 28 # 缩小图标尺寸
            padding = 2
            
            # 绘制 3x3 网格 (前两行主物品，第三行背包)
            # Row 1: items 0-2
            for i in range(3):
                if i < len(main_items):
                    url = main_items[i]
                    if url:
                        path = url_map.get(url)
                        if path and os.path.exists(path):
                            try:
                                item_img = Image.open(path).convert("RGBA")
                                item_img = item_img.resize((item_size, int(item_size * 0.72)), Image.Resampling.LANCZOS)
                                img.paste(item_img, (items_x + i * (item_size + padding), current_y), item_img)
                            except:
                                pass
            
            # Row 2: items 3-5
            for i in range(3):
                idx = i + 3
                if idx < len(main_items):
                    url = main_items[idx]
                    if url:
                        path = url_map.get(url)
                        if path and os.path.exists(path):
                            try:
                                item_img = Image.open(path).convert("RGBA")
                                item_img = item_img.resize((item_size, int(item_size * 0.72)), Image.Resampling.LANCZOS)
                                img.paste(item_img, (items_x + i * (item_size + padding), current_y + int(item_size * 0.72) + padding), item_img)
                            except:
                                pass
                                
            # Row 3: backpack items 0-2
            for i in range(3):
                if i < len(backpack_items):
                    url = backpack_items[i]
                    if url:
                        path = url_map.get(url)
                        if path and os.path.exists(path):
                            try:
                                item_img = Image.open(path).convert("RGBA")
                                item_img = item_img.resize((item_size, int(item_size * 0.72)), Image.Resampling.LANCZOS)
                                # 背包物品可以稍微变暗或者加个边框表示在背包里，这里先直接画
                                img.paste(item_img, (items_x + i * (item_size + padding), current_y + 2 * (int(item_size * 0.72) + padding)), item_img)
                            except:
                                pass

            # 中立物品 (单独放在旁边，或者放在第一行第四个位置？用户没说，默认放在右边)
            if neutral_item:
                path = url_map.get(neutral_item)
                if path and os.path.exists(path):
                    try:
                        n_size = 28 # 圆形中立物品
                        n_img = Image.open(path).convert("RGBA")
                        n_img = n_img.resize((n_size, int(n_size * 0.72)), Image.Resampling.LANCZOS)
                        # 放在 3x3 网格的右侧
                        img.paste(n_img, (items_x + 3 * (item_size + padding) + 5, current_y + int(item_size * 0.72) // 2), n_img)
                    except:
                        pass
            
            current_y += row_h
