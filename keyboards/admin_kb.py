from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

PAYMENT_METHOD_LABELS = {
    "TON_NATIVE": "TON (Native)",
    "TON_USDT": "USDT (TON Network)",
    "POL_USDT": "USDT (Polygon)",
    "POL_USDC": "USDC (Polygon)",
    "BASE_USDC": "USDC (Base)",
}

def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Список пользователей", callback_data="admin:users_list:1")
    kb.button(text="👑 VIP пользователи", callback_data="admin:vip")
    kb.button(text="📈 Наценка на подарки", callback_data="admin:markup")
    kb.button(text="⚙️ Наценка на звезды", callback_data="admin:stars_markup")
    kb.button(text="⛽️ EVM комиссия", callback_data="admin:evm_fee")
    kb.button(text="💳 Способы оплаты", callback_data="admin:payment_methods")
    kb.button(text="📦 Управление каталогом", callback_data="admin:catalog")
    kb.button(text="🤝 Партнеры и рефералы", callback_data="admin:partners:1")
    kb.button(text="📬 Заявки партнеров", callback_data="admin:applications")
    kb.button(text="💸 Заявки на вывод", callback_data="admin:withdrawals")
    kb.button(text="📊 Статистика", callback_data="admin:stats")
    kb.button(text="📢 Рассылка", callback_data="admin:broadcast")
    kb.button(text="🚫 Заблокировали бота", callback_data="admin:blocked_users:1")
    kb.button(text="🔄 Ручной возврат (Refund)", callback_data="admin:refund")
    kb.button(text="💼 Обновить кошельки", callback_data="admin:refresh_wallets")
    kb.button(text="◀️ В главное меню", callback_data="main_menu")
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 1, 1)
    return kb.as_markup()

def get_admin_payment_methods_keyboard(methods_status: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for method_key, label in PAYMENT_METHOD_LABELS.items():
        is_enabled = methods_status.get(method_key, True)
        status_icon = "🟢" if is_enabled else "🔴"
        kb.button(
            text=f"{status_icon} {label}",
            callback_data=f"admin:toggle_paymethod:{method_key}"
        )
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    kb.adjust(1)
    return kb.as_markup()

def get_admin_vip_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить VIP", callback_data="admin:vip_add")
    kb.button(text="➖ Удалить VIP", callback_data="admin:vip_remove")
    kb.button(text="📋 Список VIP", callback_data="admin:vip_list")
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    kb.adjust(2, 1, 1)
    return kb.as_markup()

def get_admin_catalog_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить подарок", callback_data="admin:cat_add")
    kb.button(text="➖ Удалить подарок", callback_data="admin:cat_remove")
    kb.button(text="📋 Все подарки", callback_data="admin:cat_list")
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    kb.adjust(2, 1, 1)
    return kb.as_markup()

def get_admin_partners_menu_keyboard(partners: list, page: int = 1, per_page: int = 8) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    total_count = len(partners)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages)) if total_count > 0 else 1
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_partners = partners[start_idx:end_idx]

    for p in page_partners:
        name = p.get("username") or p.get("first_name") or f"ID {p['user_id']}"
        status_icon = "🟢" if (p.get("is_partner") and not p.get("is_expired")) else "🔴"
        source_badge = ""
        if p.get("invited_by_promo"):
            source_badge = f" [🔗 {p['invited_by_promo']}]"
        elif p.get("referrer_id"):
            source_badge = f" [👥 от {p['referrer_id']}]"

        kb.button(
            text=f"{status_icon} {name}{source_badge} (Реф: {p.get('total_referrals', 0)} | 5+: {p.get('active_referrals_5plus', 0)})",
            callback_data=f"admin:part_card:{p['user_id']}"
        )
    
    adjust_pattern = [1] * len(page_partners)
    
    # Pagination controls
    if total_pages > 1:
        prev_cb = f"admin:partners:{page-1}" if page > 1 else "admin:noop"
        next_cb = f"admin:partners:{page+1}" if page < total_pages else "admin:noop"
        
        kb.button(text="◀️" if page > 1 else "▪️", callback_data=prev_cb)
        kb.button(text=f"📄 {page}/{total_pages}", callback_data="admin:noop")
        kb.button(text="▶️" if page < total_pages else "▪️", callback_data=next_cb)
        adjust_pattern.append(3)

    kb.button(text="🔗 Управление промо-ссылками", callback_data="admin:promo_links_list")
    kb.button(text="🔍 Найти партнера по ID", callback_data="admin:part_search")
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    adjust_pattern.extend([1, 1, 1])

    kb.adjust(*adjust_pattern)
    return kb.as_markup()

def get_admin_users_keyboard(page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    adjust_pattern = []

    if total_pages > 1:
        prev_cb = f"admin:users_list:{page-1}" if page > 1 else "admin:noop"
        next_cb = f"admin:users_list:{page+1}" if page < total_pages else "admin:noop"
        
        kb.button(text="◀️" if page > 1 else "▪️", callback_data=prev_cb)
        kb.button(text=f"📄 {page}/{total_pages}", callback_data="admin:noop")
        kb.button(text="▶️" if page < total_pages else "▪️", callback_data=next_cb)
        adjust_pattern.append(3)

    kb.button(text="🔄 Обновить", callback_data=f"admin:users_list:{page}")
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    adjust_pattern.extend([1, 1])

    kb.adjust(*adjust_pattern)
    return kb.as_markup()

def get_admin_promo_links_keyboard(promo_links: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in promo_links:
        icon = "🟢" if p.get("is_active", 1) else "🔴"
        name = p.get("name") or p["code"]
        kb.button(
            text=f"{icon} {p['code']} ({name}) | {p.get('activations_count', 0)} акт.",
            callback_data=f"admin:promo_card:{p['code']}"
        )
    kb.button(text="➕ Создать промо-ссылку", callback_data="admin:promo_create")
    kb.button(text="◀️ Назад к партнерам", callback_data="admin:partners:1")
    kb.adjust(1)
    return kb.as_markup()

def get_admin_promo_card_keyboard(code: str, is_active: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Изменить наценку на подарки", callback_data=f"admin:promo_edit_gift:{code}")
    kb.button(text="⭐️ Изменить наценку на звезды", callback_data=f"admin:promo_edit_stars:{code}")
    kb.button(text="⏳ Изменить срок действия", callback_data=f"admin:promo_edit_days:{code}")
    toggle_text = "🔴 Отключить ссылку" if is_active else "🟢 Включить ссылку"
    kb.button(text=toggle_text, callback_data=f"admin:promo_toggle:{code}")
    kb.button(text="🗑️ Удалить ссылку", callback_data=f"admin:promo_delete:{code}")
    kb.button(text="◀️ Назад к списку ссылок", callback_data="admin:promo_links_list")
    kb.adjust(1)
    return kb.as_markup()

def get_admin_promo_cancel_keyboard(code: str = "") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    back_cb = f"admin:promo_card:{code}" if code else "admin:promo_links_list"
    kb.button(text="◀️ Отмена", callback_data=back_cb)
    return kb.as_markup()

def get_admin_partner_card_keyboard(partner_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Изменить наценку на подарки", callback_data=f"admin:part_gift_markup:{partner_id}")
    kb.button(text="⭐️ Изменить наценку на звезды", callback_data=f"admin:part_stars_markup:{partner_id}")
    kb.button(text="⏳ Изменить срок (+нед / +мес)", callback_data=f"admin:part_extend:{partner_id}")
    kb.button(text="📋 Список рефералов", callback_data=f"admin:part_refs:{partner_id}")
    kb.button(text="◀️ Назад к партнерам", callback_data="admin:partners:1")
    kb.adjust(1)
    return kb.as_markup()

def get_admin_partner_extend_keyboard(partner_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="+7 дней", callback_data=f"admin:part_add_days:{partner_id}:7")
    kb.button(text="+14 дней", callback_data=f"admin:part_add_days:{partner_id}:14")
    kb.button(text="+30 дней (1 мес)", callback_data=f"admin:part_add_days:{partner_id}:30")
    kb.button(text="+60 дней (2 мес)", callback_data=f"admin:part_add_days:{partner_id}:60")
    kb.button(text="✍️ Задать число дней", callback_data=f"admin:part_custom_days:{partner_id}")
    kb.button(text="◀️ Назад в карточку", callback_data=f"admin:part_card:{partner_id}")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()

def get_admin_applications_keyboard(applications: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for app in applications:
        app_type = "Продление" if app.get("type") == "renewal" else "Вступление"
        kb.button(
            text=f"📌 {app_type} от ID {app['user_id']}",
            callback_data=f"admin:app_card:{app['id']}"
        )
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    kb.adjust(1)
    return kb.as_markup()

def get_admin_app_card_keyboard(app_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить", callback_data=f"admin:app_approve:{app_id}")
    kb.button(text="❌ Отклонить", callback_data=f"admin:app_reject:{app_id}")
    kb.button(text="◀️ Назад к заявкам", callback_data="admin:applications")
    kb.adjust(2, 1)
    return kb.as_markup()

def get_admin_duration_choice_keyboard(app_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="1 неделя (7д)", callback_data=f"admin:app_dur:{app_id}:7")
    kb.button(text="2 недели (14д)", callback_data=f"admin:app_dur:{app_id}:14")
    kb.button(text="1 месяц (30д)", callback_data=f"admin:app_dur:{app_id}:30")
    kb.button(text="2 месяца (60д)", callback_data=f"admin:app_dur:{app_id}:60")
    kb.button(text="✍️ Ввести число дней", callback_data=f"admin:app_dur_custom:{app_id}")
    kb.button(text="❌ Отмена", callback_data=f"admin:app_card:{app_id}")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()

def get_admin_withdrawals_keyboard(withdrawals: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for wd in withdrawals:
        kb.button(
            text=f"💸 {wd['amount_stars']} ⭐️ от ID {wd['user_id']}",
            callback_data=f"admin:wd_card:{wd['id']}"
        )
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    kb.adjust(1)
    return kb.as_markup()

def get_admin_withdrawal_card_keyboard(wd_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Выплачено", callback_data=f"admin:wd_approve:{wd_id}")
    kb.button(text="❌ Отклонить (с возвратом)", callback_data=f"admin:wd_reject:{wd_id}")
    kb.button(text="◀️ Назад к выводам", callback_data="admin:withdrawals")
    kb.adjust(2, 1)
    return kb.as_markup()

def get_admin_broadcast_confirm_keyboard(total_users: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🚀 Отправить всем ({total_users} чел.)", callback_data="admin:broadcast_confirm")
    kb.button(text="❌ Отменить рассылку", callback_data="admin:broadcast_cancel")
    kb.adjust(1)
    return kb.as_markup()

def get_admin_blocked_users_keyboard(page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    adjust_pattern = []

    if total_pages > 1:
        prev_cb = f"admin:blocked_users:{page-1}" if page > 1 else "admin:noop"
        next_cb = f"admin:blocked_users:{page+1}" if page < total_pages else "admin:noop"
        
        kb.button(text="◀️ Назад" if page > 1 else "▪️", callback_data=prev_cb)
        kb.button(text=f"📄 {page}/{total_pages}", callback_data="admin:noop")
        kb.button(text="Вперед ▶️" if page < total_pages else "▪️", callback_data=next_cb)
        adjust_pattern.append(3)

    kb.button(text="🔄 Обновить список", callback_data=f"admin:blocked_users:{page}")
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    adjust_pattern.extend([1, 1])

    kb.adjust(*adjust_pattern)
    return kb.as_markup()

def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад в админку", callback_data="admin_panel")
    return kb.as_markup()
