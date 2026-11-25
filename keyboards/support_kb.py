from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_support_user_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="main_menu")
    return kb.as_markup()

def get_support_admin_reply_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 Ответить пользователю", callback_data=f"support:reply:{user_id}")
    return kb.as_markup()

def get_support_admin_cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить ответ", callback_data="admin_panel")
    return kb.as_markup()
