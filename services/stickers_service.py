import os
import asyncio
import logging
import aiohttp
from typing import Optional, List, Dict
from aiogram import Bot
from aiogram.types import FSInputFile, StickerSet, Sticker
from config import STICKER_SET_NAME
from database import get_db

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stickers_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

class StickerManager:
    def __init__(self, sticker_set_name: str = STICKER_SET_NAME):
        self.sticker_set_name = sticker_set_name
        self.stickers_cache: List[Sticker] = []
        self._file_id_cache: Dict[int, str] = {}
        self._loaded = False

    async def load_stickers(self, bot: Bot) -> bool:
        """
        Loads cached Telegram file_ids from database and official sticker set.
        """
        db = get_db()
        try:
            # 1. Load cached Telegram file_ids from SQLite
            db_stickers = await db.get_all_cached_stickers()
            self._file_id_cache.update(db_stickers)
            logger.info(f"Loaded {len(self._file_id_cache)} cached gift sticker file_ids from database")
        except Exception as e:
            logger.warning(f"Could not load database sticker cache: {e}")

        # 2. Load fallback sticker set
        try:
            sticker_set: StickerSet = await bot.get_sticker_set(name=self.sticker_set_name)
            self.stickers_cache = sticker_set.stickers
            self._loaded = True
            logger.info(f"Loaded {len(self.stickers_cache)} fallback stickers from set {self.sticker_set_name}")
            return True
        except Exception as e:
            logger.warning(f"Could not load sticker set {self.sticker_set_name}: {e}")
            return False

    async def send_gift_sticker(self, bot: Bot, chat_id: int, gift_id: int) -> bool:
        """
        Sends the exact official animated .tgs sticker for any gift ID.
        1. Instant Telegram file_id (memory/db cache: ~50ms)
        2. Local .tgs disk cache (upload once and cache real Telegram file_id)
        3. Async aiohttp download from https://api.changes.tg/original/{gift_id}.tgs
        4. Fallback to sticker set
        """
        db = get_db()

        # 1. Instant Telegram file_id
        if gift_id in self._file_id_cache:
            file_id = self._file_id_cache[gift_id]
            if isinstance(file_id, str) and (file_id.endswith(".tgs") or "\\" in file_id or "/" in file_id):
                # It's a local file path
                if os.path.exists(file_id) and os.path.getsize(file_id) > 0:
                    try:
                        sent_msg = await bot.send_sticker(chat_id=chat_id, sticker=FSInputFile(file_id))
                        if sent_msg and sent_msg.sticker:
                            real_file_id = sent_msg.sticker.file_id
                            self._file_id_cache[gift_id] = real_file_id
                            await db.set_gift_sticker(gift_id, real_file_id)
                        return True
                    except Exception as e:
                        logger.warning(f"Error sending local file sticker for {gift_id}: {e}")
                        self._file_id_cache.pop(gift_id, None)
            else:
                try:
                    await bot.send_sticker(chat_id=chat_id, sticker=file_id)
                    return True
                except Exception as e:
                    logger.warning(f"Error sending sticker by cached file_id {file_id}: {e}")
                    self._file_id_cache.pop(gift_id, None)

        cached_file_tgs = os.path.join(CACHE_DIR, f"{gift_id}.tgs")

        # 2. Check local disk cache (.tgs file)
        if os.path.exists(cached_file_tgs) and os.path.getsize(cached_file_tgs) > 0:
            try:
                sent_msg = await bot.send_sticker(chat_id=chat_id, sticker=FSInputFile(cached_file_tgs))
                if sent_msg and sent_msg.sticker:
                    new_file_id = sent_msg.sticker.file_id
                    self._file_id_cache[gift_id] = new_file_id
                    await db.set_gift_sticker(gift_id, new_file_id)
                return True
            except Exception as e:
                logger.warning(f"Error sending local cached .tgs for {gift_id}: {e}")

        # 3. Asynchronously download .tgs from api.changes.tg via aiohttp
        api_url = f"https://api.changes.tg/original/{gift_id}.tgs"
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "TelegramBot/1.0 (powered by @GiftChanges)"}
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        if content:
                            with open(cached_file_tgs, "wb") as f:
                                f.write(content)
                            
                            sent_msg = await bot.send_sticker(chat_id=chat_id, sticker=FSInputFile(cached_file_tgs))
                            if sent_msg and sent_msg.sticker:
                                new_file_id = sent_msg.sticker.file_id
                                self._file_id_cache[gift_id] = new_file_id
                                await db.set_gift_sticker(gift_id, new_file_id)
                            logger.info(f"Downloaded and cached official sticker for {gift_id}")
                            return True
        except Exception as e:
            logger.info(f"api.changes.tg async download for {gift_id}: {e}")

        # 4. Fallback to sticker set
        if not self._loaded or not self.stickers_cache:
            await self.load_stickers(bot)

        if self.stickers_cache:
            index = abs(hash(str(gift_id))) % len(self.stickers_cache)
            try:
                await bot.send_sticker(chat_id=chat_id, sticker=self.stickers_cache[index].file_id)
                return True
            except Exception as e:
                logger.warning(f"Error sending fallback pack sticker: {e}")

        return False

    async def prefetch_stickers_in_background(self):
        """
        Background task: downloads all 120 official .tgs files from api.changes.tg
        into stickers_cache/ in parallel without blocking user requests.
        """
        await asyncio.sleep(2)
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "TelegramBot/1.0 (powered by @GiftChanges)"}
                async with session.get("https://api.changes.tg/ids", headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return
                    ids_data = await resp.json(content_type=None)
                    
            semaphore = asyncio.Semaphore(5)


            async def download_one(gid_str: str):
                cached_path = os.path.join(CACHE_DIR, f"{gid_str}.tgs")
                if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0:
                    return
                async with semaphore:
                    try:
                        async with aiohttp.ClientSession() as sess:
                            url = f"https://api.changes.tg/original/{gid_str}.tgs"
                            async with sess.get(url, headers={"User-Agent": "TelegramBot/1.0 (powered by @GiftChanges)"}, timeout=aiohttp.ClientTimeout(total=5)) as r:
                                if r.status == 200:
                                    data = await r.read()
                                    with open(cached_path, "wb") as f:
                                        f.write(data)
                    except Exception:
                        pass

            tasks = [download_one(gid) for gid in ids_data.keys()]
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Background sticker pre-fetch completed successfully!")
        except Exception as e:
            logger.warning(f"Background sticker prefetch error: {e}")

sticker_manager = StickerManager()
