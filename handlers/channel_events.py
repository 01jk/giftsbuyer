import logging
from aiogram import Router, Bot
from aiogram.types import ChatMemberUpdated
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, MEMBER, KICKED, LEFT, RESTRICTED, ADMINISTRATOR, CREATOR

from database.db import get_db

logger = logging.getLogger("ChannelEvents")
router = Router(name="channel_events")


@router.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=(MEMBER | KICKED | LEFT | RESTRICTED) >> (ADMINISTRATOR | CREATOR)
    )
)
async def on_bot_promoted_to_admin(event: ChatMemberUpdated, bot: Bot):
    """
    Triggered when a user adds the bot to a channel / supergroup and makes it an administrator.
    Binds the channel to the user who performed the promotion.
    """
    chat = event.chat
    from_user = event.from_user

    # We only care about channels and supergroups
    if chat.type not in ["channel", "supergroup"]:
        return

    db = get_db()
    is_private = (chat.username is None)
    
    logger.info(
        f"Bot promoted to admin in {chat.type} '{chat.title}' (ID: {chat.id}) by user {from_user.id} (@{from_user.username})"
    )

    await db.add_user_channel(
        user_id=from_user.id,
        channel_id=chat.id,
        channel_title=chat.title or "Без названия",
        channel_username=chat.username,
        is_private=is_private
    )

    # Notify user in private chat
    try:
        channel_name_display = f"@{chat.username}" if chat.username else f"«{chat.title}»"
        text = (
            f"🎉 <b>Канал {channel_name_display} успешно привязан!</b>\n\n"
            f"📢 <b>Название:</b> {chat.title}\n"
            f"🆔 <b>ID канала:</b> <code>{chat.id}</code>\n"
            f"🔒 <b>Тип:</b> {'Закрытый (приватный)' if is_private else 'Открытый (публичный)'}\n\n"
            f"Теперь при оформлении заказа вы можете выбрать <b>«📢 Для канала»</b> и отправить подарки прямо в этот канал в 1 клик!"
        )
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="📢 Перейти к списку каналов", callback_data="recipient:channel")
        await bot.send_message(
            chat_id=from_user.id,
            text=text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Could not send channel link confirmation to user {from_user.id}: {e}")


@router.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=(ADMINISTRATOR | CREATOR) >> (MEMBER | KICKED | LEFT | RESTRICTED)
    )
)
async def on_bot_demoted_or_removed(event: ChatMemberUpdated, bot: Bot):
    """
    Triggered when the bot is removed from a channel or demoted from administrator status.
    Deactivates the channel in the database.
    """
    chat = event.chat
    from_user = event.from_user

    if chat.type not in ["channel", "supergroup"]:
        return

    db = get_db()
    logger.info(f"Bot demoted/removed from {chat.type} '{chat.title}' (ID: {chat.id})")
    await db.deactivate_user_channel(channel_id=chat.id)

    try:
        text = (
            f"ℹ️ Бот был удален или лишён прав администратора в канале <b>«{chat.title}»</b>.\n"
            f"Канал отключен от быстрой отправки подарков."
        )
        await bot.send_message(chat_id=from_user.id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Could not send channel demote notification to user {from_user.id}: {e}")
