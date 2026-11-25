from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_partner_cabinet_keyboard(is_active: bool, is_expired: bool, balance: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if is_active:
        kb.button(text="💸 Вывести средства", callback_data="partner:withdraw")
        kb.button(text="📋 Список рефералов", callback_data="partner:referrals_list")
        kb.button(text="🔄 Обновить", callback_data="partner:open")
        kb.button(text="◀️ В главное меню", callback_data="main_menu")
        kb.adjust(1, 1, 2)
    elif is_expired:
        kb.button(text="🔄 Подать заявку на продление", callback_data="partner:request_renewal")
        if balance >= 1000:
            kb.button(text="💸 Вывести средства", callback_data="partner:withdraw")
        kb.button(text="📋 Список рефералов", callback_data="partner:referrals_list")
        kb.button(text="◀️ В главное меню", callback_data="main_menu")
        kb.adjust(1)
    else:
        kb.button(text="📝 Подать заявку на участие", callback_data="partner:apply_new")
        kb.button(text="◀️ В главное меню", callback_data="main_menu")
        kb.adjust(1)
    return kb.as_markup()

def get_withdrawal_memo_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏩ Пропустить Memo", callback_data="partner:skip_memo")
    kb.button(text="❌ Отмена", callback_data="partner:open")
    kb.adjust(1)
    return kb.as_markup()

def get_partner_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад в кабинет", callback_data="partner:open")
    kb.button(text="🏠 В главное меню", callback_data="main_menu")
    kb.adjust(1, 1)
    return kb.as_markup()
