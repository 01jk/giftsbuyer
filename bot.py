import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

import aiohttp
from aiogram.client.session.aiohttp import AiohttpSession

# Monkey-patch aiohttp.TCPConnector to ALWAYS use ThreadedResolver (fixes Windows DNS issues)
original_init = aiohttp.TCPConnector.__init__
def patched_init(self, *args, **kwargs):
    if 'resolver' not in kwargs:
        kwargs['resolver'] = aiohttp.ThreadedResolver()
    original_init(self, *args, **kwargs)
aiohttp.TCPConnector.__init__ = patched_init
from config import BOT_TOKEN, STICKER_SET_NAME, PROXY
from database import get_db
from services.stickers_service import sticker_manager
from services.ton_scanner import ton_scanner
from handlers import (
    admin_router,
    start_router,
    partner_router,
    support_router,
    catalog_router,
    gift_flow_router,
    buy_stars_router,
    channel_events_router
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("GiftsBuyerBot")

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment or config.py! Please add BOT_TOKEN.")
        print("\n[!] ОШИБКА: Токен бота не указан в .env или config.py!")
        print("[!] Пожалуйста, добавьте BOT_TOKEN=ваш_токен в файл .env\n")
        return

    logger.info("Initializing database...")
    db = get_db()
    await db.init_db()
    logger.info("Database initialized successfully.")

    # Create resilient session with ThreadedResolver (fixes Windows aiodns resolution issues)
    session = AiohttpSession(proxy=PROXY)
    session._connector_init["resolver"] = aiohttp.ThreadedResolver()

    # Initialize Bot and Dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register routers in priority order
    dp.include_router(admin_router)
    dp.include_router(channel_events_router)
    dp.include_router(start_router)
    dp.include_router(partner_router)
    dp.include_router(support_router)
    dp.include_router(catalog_router)
    dp.include_router(gift_flow_router)
    dp.include_router(buy_stars_router)

    # Background partner expiry checker
    async def background_partner_expiry_checker(bot_instance: Bot):
        while True:
            try:
                db_inst = get_db()
                expired_partners = await db_inst.get_expired_unnotified_partners()
                for p in expired_partners:
                    u_id = p["user_id"]
                    try:
                        from keyboards.partner_kb import get_partner_cabinet_keyboard
                        text = (
                            "⌛️ <b>Срок действия вашей партнерской программы завершился!</b>\n\n"
                            "Вы можете отправить заявку на продление партнерской программы администрации.\n"
                            "Администрация проверит вашу реферальную активность и вынесет решение."
                        )
                        kb = get_partner_cabinet_keyboard(is_active=False, is_expired=True, balance=p.get("partner_balance", 0) or 0)
                        await bot_instance.send_message(chat_id=u_id, text=text, reply_markup=kb, parse_mode="HTML")
                        await db_inst.mark_partner_expiry_notified(u_id)
                    except Exception as ex:
                        logger.warning(f"Failed to notify expired partner {u_id}: {ex}")
            except Exception as e:
                logger.warning(f"Error in background_partner_expiry_checker: {e}")
            await asyncio.sleep(3600)

    asyncio.create_task(background_partner_expiry_checker(bot))

    # Pre-cache stickers from sticker pack and sync catalog
    try:
        await sticker_manager.load_stickers(bot)
        
        async def background_sync(bot_instance):
            try:
                from services.catalog_service import catalog_service
                from services.channel_sync import sync_stickers_from_channel
                from services.telethon_service import TelethonService
                
                await catalog_service.sync_catalog_from_api()
                await TelethonService.sync_catalog_to_db()
                await sync_stickers_from_channel(bot_instance)
                await sticker_manager.prefetch_stickers_in_background()
            except Exception as e:
                logger.warning(f"Error in background sync: {e}")
            
        asyncio.create_task(background_sync(bot))
    except Exception as e:
        logger.warning(f"Could not preload stickers or catalog: {e}")



    # Start TON blockchain background scanner
    ton_scanner.start()

    bot_user = await bot.get_me()
    logger.info(f"Bot @{bot_user.username} (ID: {bot_user.id}) started successfully!")
    print(f"\n[+] Бот @{bot_user.username} успешно запущен и готов к работе!\n")

    # Start polling
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Stopping TON background scanner...")
        await ton_scanner.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
