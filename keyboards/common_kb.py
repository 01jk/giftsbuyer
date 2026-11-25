from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_start_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Купить подарок", callback_data="catalog:open")
    kb.button(text="⭐️ Купить Звезды", callback_data="buy_stars_start")
    kb.button(text="🤝 Партнерская программа", callback_data="partner:open")
    kb.button(text="💬 Поддержка", callback_data="support:open")
    kb.button(text="ℹ️ Как это работает", callback_data="help_info")
    if is_admin:
        kb.button(text="⚙️ Админ панель", callback_data="admin_panel")
    kb.adjust(1)
    return kb.as_markup()

def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ В главное меню", callback_data="main_menu")
    return kb.as_markup()

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel_order")
    return kb.as_markup()
