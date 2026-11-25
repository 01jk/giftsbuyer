from typing import List, Dict, Any, Optional
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_recipient_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Для себя", callback_data="recipient:self")
    kb.button(text="👥 Для друга", callback_data="recipient:friend")
    kb.button(text="📢 Для канала", callback_data="recipient:channel")
    kb.button(text="❌ Отмена", callback_data="cancel_order")
    kb.adjust(2, 1, 1)
    return kb.as_markup()

def get_channel_selection_keyboard(channels: List[Dict[str, Any]], bot_username: str = "") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in channels:
        title = ch.get("channel_title") or f"Канал {ch['channel_id']}"
        if len(title) > 28:
            title = title[:25] + "..."
        kb.button(text=f"📢 {title}", callback_data=f"channel_select:{ch['channel_id']}")
    
    if bot_username:
        kb.button(
            text="➕ Добавить бота в закрытый канал",
            url=f"https://t.me/{bot_username}?startchannel=bot&admin=change_info+post_messages"
        )
    kb.button(text="🔄 Обновить список каналов", callback_data="recipient:channel")
    kb.button(text="✍️ Ввести @username открытого канала", callback_data="channel_manual")
    kb.button(text="ℹ️ Инструкция по привязке", callback_data="channel_bind_info")
    kb.button(text="🔙 Назад к выбору", callback_data="channel_back_to_recipient")
    kb.button(text="❌ Отмена", callback_data="cancel_order")
    
    # Layout:
    # 1. Each channel button on its own row
    # 2. Add bot button (1 row, if bot_username present)
    # 3. Refresh channels button (1 row)
    # 4. Manual username button (1 row)
    # 5. Instructions button (1 row)
    # 6. Back & Cancel buttons (2 side-by-side)
    sizes = [1] * len(channels) + ([1] if bot_username else []) + [1, 1, 1, 2]
    kb.adjust(*sizes)
    return kb.as_markup()

def get_add_channel_keyboard(bot_username: str = "") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if bot_username:
        kb.button(
            text="➕ Добавить бота в канал",
            url=f"https://t.me/{bot_username}?startchannel=bot&admin=change_info+post_messages"
        )
    kb.button(text="🔄 Проверить привязку", callback_data="recipient:channel")
    kb.button(text="🔙 Назад к каналам", callback_data="recipient:channel")
    kb.button(text="❌ Отмена", callback_data="cancel_order")
    kb.adjust(1, 1, 2)
    return kb.as_markup()

def get_signature_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Добавить сообщение", callback_data="signature:add")
    kb.button(text="➡️ Без подписи", callback_data="signature:none")
    kb.button(text="❌ Отмена", callback_data="cancel_order")
    kb.adjust(2, 1)
    return kb.as_markup()
