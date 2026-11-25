import os
import logging
import asyncio
from telethon import TelegramClient
from telethon.errors import (
    RPCError,
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError
)
from telethon.tl.functions.payments import GetPaymentFormRequest, SendStarsFormRequest, GetStarGiftsRequest
from telethon.tl.types import InputInvoiceStarGift, TextWithEntities
from typing import Optional, Tuple, Dict, Any, List, Union

from config import API_ID, API_HASH, BOT_MASTER_SESSION, BOT_TOKEN
from database import get_db

logger = logging.getLogger(__name__)

# Cache for GetStarGiftsRequest
_GIFTS_CACHE = {"timestamp": 0, "gifts": []}



ORIGINAL_HIDDEN_GIFTS = [
    {"gift_id": 6046178578163303744, "title": "Celebration Cake", "stars": 50, "emoji_id": "5470129614439362117"},
    {"gift_id": 5974210632977745012, "title": "Teddy Bear", "stars": 50, "emoji_id": "5397971251878732060"},
    {"gift_id": 6026193266406327981, "title": "Surprise Box", "stars": 50, "emoji_id": "5447213743417105726"},
    {"gift_id": 5969796561943660080, "title": "Holiday Box", "stars": 50, "emoji_id": "5393309541620291208"},
    {"gift_id": 5935895822435615975, "title": "Special Gift", "stars": 50, "emoji_id": "5359736160224586485"},
    {"gift_id": 5893356958802511476, "title": "Golden Box", "stars": 50, "emoji_id": "5317000922096769303"},
    {"gift_id": 5866352046986232958, "title": "Classic Bear", "stars": 50, "emoji_id": "5294268489127731562"},
    {"gift_id": 5800655655995968830, "title": "Secret Gift", "stars": 50, "emoji_id": "5226661632259691727"},
    {"gift_id": 5801108895304779062, "title": "Mystery Box", "stars": 50, "emoji_id": "5224628072619216265"},
    {"gift_id": 5956217000635139069, "title": "Wonder Box", "stars": 50, "emoji_id": "5379850840691476775"},
    {"gift_id": 5922558454332916696, "title": "Xmas Pine", "stars": 50, "emoji_id": "5345935030143196497"},
]

class TelethonService:
    @staticmethod
    async def get_master_client() -> TelegramClient:


        session_name = BOT_MASTER_SESSION.replace(".session", "")
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        return client

    @staticmethod
    async def get_master_session_status() -> Tuple[bool, str]:
        try:
            client = await TelethonService.get_master_client()
            if await client.is_user_authorized():
                me = await client.get_me()
                name = me.first_name or "Master"
                username = f"@{me.username}" if me.username else f"ID: {me.id}"
                await client.disconnect()
                return True, f"Авторизована ({name}, {username})"
            await client.disconnect()
            return False, "Не авторизована (запустите python login_master.py)"
        except Exception as e:
            return False, f"Ошибка: {e}"



    @staticmethod
    async def check_gift_availability(gift_id: int) -> Tuple[bool, int, str]:
        """
        Checks if gift is available and fetches its exact price via Telegram MTProto API.
        Returns: (is_available, price_in_stars, message_status)
        """
        # 1. First check if it is one of our special hidden gifts
        hidden_map = {g["gift_id"]: g for g in ORIGINAL_HIDDEN_GIFTS}
        if gift_id in hidden_map:
            stars = hidden_map[gift_id].get("stars", 50)
            return True, stars, "✅ Доступен к покупке"

        # 2. Check live Telegram MTProto store gifts
        import time
        now = time.time()
        global _GIFTS_CACHE

        gifts_list = _GIFTS_CACHE.get("gifts", [])
        if not gifts_list or (now - _GIFTS_CACHE.get("timestamp", 0)) > 60:
            client = TelegramClient("temp_gifts_checker", API_ID, API_HASH)
            try:
                await client.start(bot_token=BOT_TOKEN)
                res = await client(GetStarGiftsRequest(hash=0))
                gifts_list = res.gifts
                _GIFTS_CACHE["gifts"] = gifts_list
                _GIFTS_CACHE["timestamp"] = now
            except Exception as e:
                logger.warning(f"Error refreshing MTProto gifts cache: {e}")
            finally:
                await client.disconnect()

        # Find the gift in the live Telegram gifts response
        gift_obj = next((g for g in gifts_list if g.id == gift_id), None)
        
        if gift_obj:
            is_sold_out = getattr(gift_obj, "sold_out", False) or (
                getattr(gift_obj, "availability_remains", None) is not None and getattr(gift_obj, "availability_remains", None) <= 0
            )
            stars = gift_obj.stars
            total = getattr(gift_obj, "availability_total", None)
            remains = getattr(gift_obj, "availability_remains", None)
            
            if is_sold_out:
                total_str = f" (0 из {total:,})" if total else ""
                return False, stars, f"❌ Подарок уже распродан{total_str}"
            
            if remains is not None and total:
                return True, stars, f"✅ Доступен к покупке ({remains:,} из {total:,})"
            
            return True, stars, "✅ Доступен к покупке"

        return False, 0, "❌ Подарок распродан или не найден"

    @staticmethod
    async def sync_catalog_to_db():
        """
        Fetches all gifts via MTProto and saves them to the catalog DB with real prices.
        """
        client = TelegramClient("temp_catalog_sync", API_ID, API_HASH)
        try:
            await client.start(bot_token=BOT_TOKEN)
            res = await client(GetStarGiftsRequest(hash=0))
            gifts_list = res.gifts
            
            from database.db import get_db
            from services.catalog_service import ID_TO_NAME
            db = get_db()
            
            db_gifts = []
            seen_ids = set()
            hidden_ids_map = {g["gift_id"]: g for g in ORIGINAL_HIDDEN_GIFTS}
            
            # 1. Add gifts from live MTProto list
            for g in gifts_list:
                seen_ids.add(g.id)
                if g.id in hidden_ids_map:
                    hg = hidden_ids_map[g.id]
                    db_gifts.append({
                        "gift_id": g.id,
                        "title": hg.get("title") or ID_TO_NAME.get(g.id, f"Gift #{g.id}"),
                        "stars": hg.get("stars", g.stars),
                        "emoji_id": hg.get("emoji_id"),
                        "is_active": 1
                    })
                else:
                    title = ID_TO_NAME.get(g.id, f"Gift #{g.id}")
                    is_sold_out = getattr(g, "sold_out", False) or (
                        getattr(g, "availability_remains", None) is not None and getattr(g, "availability_remains", None) <= 0
                    )
                    db_gifts.append({
                        "gift_id": g.id,
                        "title": title,
                        "stars": g.stars,
                        "is_active": 0 if is_sold_out else 1
                    })
                
            # 2. Add our 11 hidden gifts if not seen in MTProto
            for g in ORIGINAL_HIDDEN_GIFTS:
                if g["gift_id"] not in seen_ids:
                    db_gifts.append({
                        "gift_id": g["gift_id"],
                        "title": g["title"],
                        "stars": g["stars"],
                        "emoji_id": g.get("emoji_id"),
                        "is_active": 1
                    })
                
            if db_gifts:
                await db.sync_catalog_gifts(db_gifts)
                logger.info(f"Synced {len(db_gifts)} gifts to DB catalog (hidden gifts + active store gifts).")
                
            # Now run auto-match since DB is populated
            matched_count = await db.auto_match_emojis()
            if matched_count > 0:
                logger.info(f"Automatically matched {matched_count} custom emojis from cache!")
        except Exception as e:
            logger.warning(f"Error syncing catalog to DB: {e}")
        finally:
            await client.disconnect()

    @staticmethod
    async def send_gifts_from_master_bot(
        gifts_list: Union[List[int], List[Dict[str, Any]], int],
        target_peer: str,
        is_anonymous: bool = False,
        message_text: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Sends multiple gifts sequentially in exact order using the bot master account.
        """
        if isinstance(gifts_list, (int, str)):
            clean_ids = [int(gifts_list)]
        else:
            clean_ids = [g["gift_id"] if isinstance(g, dict) else int(g) for g in gifts_list]

        if not clean_ids:
            return False, "Список подарков пуст."

        client = await TelethonService.get_master_client()
        try:
            if not await client.is_user_authorized():
                return False, "Мастер-сессия бота не авторизована. Обратитесь к администратору."

            try:
                # Handle numeric peer vs username
                if target_peer.lstrip("-").isdigit():
                    peer = await client.get_input_entity(int(target_peer))
                else:
                    peer = await client.get_input_entity(target_peer)
            except Exception as e:
                return False, f"Не удалось найти получателя '{target_peer}': {e}"

            msg_obj = TextWithEntities(text=message_text, entities=[]) if message_text else None
            
            sent_count = 0
            for idx, gid in enumerate(clean_ids, 1):
                invoice = InputInvoiceStarGift(
                    peer=peer,
                    gift_id=gid,
                    hide_name=is_anonymous,
                    message=msg_obj
                )

                form = await client(GetPaymentFormRequest(invoice=invoice))
                await client(SendStarsFormRequest(
                    form_id=form.form_id,
                    invoice=invoice
                ))
                sent_count += 1
                logger.info(f"Master bot sent gift {gid} ({sent_count}/{len(clean_ids)}) to {target_peer}")
                if idx < len(clean_ids):
                    await asyncio.sleep(1.2)

            return True, f"Все подарки ({sent_count} шт.) успешно отправлены!"

        except RPCError as e:
            logger.error(f"RPCError sending gift from master: {e}")
            return False, f"Ошибка Telegram API: {e}"
        except Exception as e:
            logger.error(f"General error sending gift from master: {e}")
            return False, f"Ошибка отправки: {e}"
        finally:
            await client.disconnect()

    @staticmethod
    async def send_gift_from_master_bot(
        gift_id: int,
        target_peer: str,
        is_anonymous: bool = False,
        message_text: Optional[str] = None
    ) -> Tuple[bool, str]:
        return await TelethonService.send_gifts_from_master_bot(
            gifts_list=[gift_id],
            target_peer=target_peer,
            is_anonymous=is_anonymous,
            message_text=message_text
        )

    # --- User Account Authentication & Buying Flow ---
