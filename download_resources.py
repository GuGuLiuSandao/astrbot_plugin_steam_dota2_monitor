import asyncio
import aiohttp
import os
import json

# API 端点
OPENDOTA_API_BASE = "https://api.opendota.com/api"
# Valve CDN for images (avoids OpenDota rate limits)
VALVE_CDN_BASE = "https://cdn.cloudflare.steamstatic.com"

# 本地保存路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEROES_DIR = os.path.join(BASE_DIR, "resources", "images", "heroes")
ITEMS_DIR = os.path.join(BASE_DIR, "resources", "images", "items")

# 确保目录存在
os.makedirs(HEROES_DIR, exist_ok=True)
os.makedirs(ITEMS_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

async def download_file(session, url, filepath):
    if not url:
        return
    
    # 如果文件已存在且大小不为0，跳过
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        print(f"Skipping (exists): {filepath}")
        return

    try:
        async with session.get(url, headers=HEADERS, timeout=15) as resp:
            if resp.status == 200:
                content = await resp.read()
                with open(filepath, "wb") as f:
                    f.write(content)
                print(f"Downloaded: {filepath}")
            else:
                print(f"Failed to download {url}: Status {resp.status}")
    except Exception as e:
        print(f"Error downloading {url}: {e}")

async def download_heroes(session):
    print("Fetching heroes list...")
    async with session.get(f"{OPENDOTA_API_BASE}/constants/heroes", headers=HEADERS) as resp:
        if resp.status != 200:
            print(f"Failed to fetch heroes list: {resp.status}")
            return
        heroes = await resp.json()

    tasks = []
    for hero_id, data in heroes.items():
        # OpenDota img path: /apps/dota2/images/heroes/antimage_full.png?
        img_path = data.get('img')
        if not img_path:
            continue
        
        # 去掉查询参数
        if '?' in img_path:
            img_path = img_path.split('?')[0]
            
        url = f"{VALVE_CDN_BASE}{img_path}"
        filename = os.path.basename(img_path)
        filepath = os.path.join(HEROES_DIR, filename)
        
        tasks.append(download_file(session, url, filepath))
    
    print(f"Downloading {len(tasks)} hero images...")
    await asyncio.gather(*tasks)

async def download_items(session):
    print("Fetching items list...")
    async with session.get(f"{OPENDOTA_API_BASE}/constants/items", headers=HEADERS) as resp:
        if resp.status != 200:
            print(f"Failed to fetch items list: {resp.status}")
            return
        items = await resp.json()

    tasks = []
    for item_name, data in items.items():
        img_path = data.get('img')
        if not img_path:
            continue
            
        # 去掉查询参数
        if '?' in img_path:
            img_path = img_path.split('?')[0]
            
        url = f"{VALVE_CDN_BASE}{img_path}"
        filename = os.path.basename(img_path)
        filepath = os.path.join(ITEMS_DIR, filename)
        
        tasks.append(download_file(session, url, filepath))
    
    print(f"Downloading {len(tasks)} item images...")
    await asyncio.gather(*tasks)

async def main():
    async with aiohttp.ClientSession() as session:
        await download_heroes(session)
        await download_items(session)
    print("All downloads completed!")

if __name__ == "__main__":
    asyncio.run(main())
