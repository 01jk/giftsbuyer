import urllib.request
import re
import os
import logging
import asyncio
from typing import Dict
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from aiogram import Bot
from config import BOT_TOKEN, DB_PATH
from database import get_db

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stickers_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

async def sync_stickers_from_channel(bot: Bot):
    """
    Scrapes all posts from https://t.me/s/GiftChangesIDs,
    extracts gift_id <-> custom_emoji_id pairs,
    downloads the exact official animated .tgs sticker for each gift,
    and saves the mapping to the database.
    """
    if not BeautifulSoup:
        logger.warning("BeautifulSoup (bs4) is not installed. Skipping channel sticker sync.")
        return
    logger.info("Starting automatic sticker synchronization from https://t.me/s/GiftChangesIDs ...")
    base_url = "https://t.me/s/GiftChangesIDs"
    current_url = base_url
    all_pairs: Dict[int, str] = {}

    # Scrape multiple pages
    for page in range(10):
        try:
            req = urllib.request.Request(current_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8")
                soup = BeautifulSoup(html, "html.parser")
                messages = soup.find_all("div", class_="tgme_widget_message_text")
                
                if not messages:
                    break

                for msg in messages:
                    raw_html = str(msg)
                    matches = re.findall(r'emoji-id=["\'](\d+)["\'].*?(\d{10,25})', raw_html, re.DOTALL)
                    for emoji_id, gift_id in matches:
                        all_pairs[int(gift_id)] = str(emoji_id)

                prev_link = soup.find("link", rel="prev")
                if prev_link and prev_link.get("href"):
                    href = prev_link.get("href")
                    current_url = "https://t.me" + href if href.startswith("/") else href
                else:
                    break
        except Exception as e:
            logger.warning(f"Error scraping channel page {page}: {e}")
            break

    logger.info(f"Extracted {len(all_pairs)} gift IDs with custom emojis from @GiftChangesIDs")

    if not all_pairs:
        return

    db = get_db()
    
    # Download stickers in chunks of 50 via bot.get_custom_emoji_stickers
    emoji_ids_list = list(set(all_pairs.values()))
    chunk_size = 50
    emoji_to_path = {}

    for i in range(0, len(emoji_ids_list), chunk_size):
        chunk = emoji_ids_list[i:i + chunk_size]
        try:
            stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=chunk)
            for s in stickers:
                local_path = os.path.join(CACHE_DIR, f"custom_{s.custom_emoji_id}.tgs")
                if not os.path.exists(local_path):
                    try:
                        file_info = await bot.get_file(s.file_id)
                        if file_info.file_path:
                            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
                            urllib.request.urlretrieve(file_url, local_path)
                    except Exception as e:
                        logger.warning(f"Error downloading sticker {s.custom_emoji_id}: {e}")
                
                if os.path.exists(local_path):
                    emoji_to_path[str(s.custom_emoji_id)] = local_path
        except Exception as e:
            logger.warning(f"Error fetching custom emoji chunk: {e}")

    # Bind emojis to catalog in database
    bound_count = 0
    for gift_id, emoji_id in all_pairs.items():
        await db.update_catalog_emoji(gift_id, emoji_id)
        bound_count += 1

    logger.info(f"Successfully bound {bound_count} gifts to custom emojis from @GiftChangesIDs!")
