import datetime
import logging
import asyncio
import time
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError
from config import ADMIN_IDS
from database import get_db
from states.gift_states import (
    AdminState,
    AdminPartnerState,
    AdminApplicationDecisionState,
    AdminWithdrawalDecisionState,
    AdminBroadcastState,
    AdminPromoCreateState,
    AdminPromoEditState
)
from services.payment_service import PaymentService
from keyboards.admin_kb import (
    get_admin_main_keyboard,
    get_admin_vip_keyboard,
    get_admin_catalog_keyboard,
    get_admin_back_keyboard,
    get_admin_payment_methods_keyboard,
    PAYMENT_METHOD_LABELS,
    get_admin_partners_menu_keyboard,
    get_admin_partner_card_keyboard,
    get_admin_partner_extend_keyboard,
    get_admin_applications_keyboard,
    get_admin_app_card_keyboard,
    get_admin_duration_choice_keyboard,
    get_admin_withdrawals_keyboard,
    get_admin_withdrawal_card_keyboard,
    get_admin_broadcast_confirm_keyboard,
    get_admin_blocked_users_keyboard,
    get_admin_users_keyboard,
    get_admin_promo_links_keyboard,
    get_admin_promo_card_keyboard,
    get_admin_promo_cancel_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

def is_admin_filter(event: Message | CallbackQuery) -> bool:
    user_id = event.from_user.id
    return user_id in ADMIN_IDS

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    await state.clear()
    await show_admin_panel(message)

@router.message(Command("setsticker"))
async def cmd_set_sticker(message: Message, bot: Bot):
    if not is_admin_filter(message):
        return
    
    parts = message.text.strip().split()
    db = get_db()
    from services.stickers_service import sticker_manager

    # 1. Check if replying to a sticker: /setsticker <gift_id>
    if message.reply_to_message and message.reply_to_message.sticker:
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("⚠️ Использование в ответе на стикер: <code>/setsticker ID_ПОДАРКА</code>", parse_mode="HTML")
            return
        gift_id = int(parts[1])
        file_id = message.reply_to_message.sticker.file_id
        await db.set_gift_sticker(gift_id, file_id)
        await message.answer(f"✅ Стикер для подарка <code>{gift_id}</code> успешно сохранен!", parse_mode="HTML")
        return

    # 2. Or /setsticker <gift_id> <sticker_index_0_to_43>
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer(
            "⚠️ <b>Использование команды:</b>\n"
            "1. <code>/setsticker ID_ПОДАРКА НОМЕР_СТИКЕРА</code> (от 0 до 43)\n"
            "2. Или ответьте командой <code>/setsticker ID_ПОДАРКА</code> на любой стикер в чате.",
            parse_mode="HTML"
        )
        return

    gift_id = int(parts[1])
    idx = int(parts[2])

    if not sticker_manager._loaded or not sticker_manager.stickers_cache:
        await sticker_manager.load_stickers(bot)

    if 0 <= idx < len(sticker_manager.stickers_cache):
        file_id = sticker_manager.stickers_cache[idx].file_id
        await db.set_gift_sticker(gift_id, file_id)
        await message.answer(f"✅ Стикер #{idx} для подарка <code>{gift_id}</code> успешно привязан!", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Номер стикера должен быть от 0 до {len(sticker_manager.stickers_cache) - 1}")

@router.message(Command("syncchannel"))
async def cmd_sync_channel(message: Message, bot: Bot):
    if not is_admin_filter(message):
        return
    msg = await message.answer("🔄 Запущена синхронизация стикеров из канала @GiftChangesIDs...")
    from services.channel_sync import sync_stickers_from_channel
    try:
        await sync_stickers_from_channel(bot)
        await msg.edit_text("✅ Синхронизация стикеров из канала @GiftChangesIDs успешно завершена!")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка синхронизации: {e}")



@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
    await state.clear()
    await show_admin_panel(callback.message)
    await callback.answer()

@router.callback_query(F.data == "admin:refresh_wallets")
async def cb_admin_refresh_wallets(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    await callback.message.edit_text("🔄 Обновляю данные кошельков...")
    await show_admin_panel(callback.message, refresh_wallets=True)
    await callback.answer("Кошельки обновлены!")

async def show_admin_panel(message: Message, refresh_wallets: bool = False):
    db = get_db()
    markup = await db.get_markup_percent()
    stars_markup = await db.get_stars_markup_percent()
    stats = await db.get_stats()
    
    from services.telethon_service import TelethonService
    from services.evm_checker import evm_checker
    from services.ton_checker import ton_checker
    from services.fragment_service import fragment_service
    
    is_master_auth, master_info = await TelethonService.get_master_session_status()
    master_badge = f"🟢 {master_info}" if is_master_auth else f"🔴 {master_info}"

    if refresh_wallets:
        evm_balances = await evm_checker.get_balances()
        evm_text = ", ".join([f"{k}: {v:.3f}" for k, v in evm_balances.items()]) or "0"
        
        ton_address = await fragment_service.get_wallet_address() or ""
        ton_balances = await ton_checker.get_balances(ton_address) if ton_address else {"TON": 0.0, "USDT": 0.0}
        ton_text = f"TON: {ton_balances['TON']:.3f}, USDT: {ton_balances['USDT']:.3f}"
    else:
        evm_text = "<i>Нажмите «Обновить кошельки»</i>"
        ton_text = "<i>Нажмите «Обновить кошельки»</i>"

    methods_status = await db.get_payment_methods_status()
    active_methods_count = sum(1 for v in methods_status.values() if v)
    total_methods_count = len(methods_status)
    methods_badge = f"{active_methods_count}/{total_methods_count} активны"

    blocked_info = f" (🚫 Блок: <code>{stats.get('blocked_count', 0)}</code>)" if stats.get("blocked_count", 0) > 0 else ""
    text = (
        "⚙️ <b>Панель администратора</b>\n\n"
        f"🤖 <b>Мастер-сессия (для отправки 'От бота'):</b>\n{master_badge}\n\n"
        f"📈 <b>Наценка на подарки:</b> <code>{markup}%</code>\n"
        f"⚙️ <b>Наценка на звезды:</b> <code>{stars_markup}%</code>\n"
        f"💳 <b>Способы оплаты:</b> <code>{methods_badge}</code>\n\n"
        f"👥 <b>Пользователей:</b> <code>{stats['users_count']}</code>{blocked_info} | 👑 <b>VIP:</b> <code>{stats['vip_count']}</code>\n"
        f"🛍️ <b>Успешных заказов:</b> <code>{stats['completed_orders']}</code>\n"
        f"💎 <b>Заработано (комиссия):</b> <code>{stats['total_earned_stars']} ⭐️</code>\n"
        f"⭐️ <b>Продано звезд:</b> <code>{stats.get('sold_stars', 0)} ⭐️</code>\n\n"
        f"💰 <b>EVM баланс:</b> <code>{evm_text}</code>\n"
        f"💎 <b>TON баланс:</b> <code>{ton_text}</code>\n\n"
        "Выберите раздел для управления:"
    )

    try:
        await message.edit_text(text, reply_markup=get_admin_main_keyboard(), parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=get_admin_main_keyboard(), parse_mode="HTML")


# --- VIP Management ---
@router.callback_query(F.data == "admin:vip")
async def cb_admin_vip(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    text = (
        "👑 <b>Управление VIP-пользователями</b>\n\n"
        "VIP-пользователи могут покупать любые подарки <b>по себестоимости (0% комиссии)</b>.\n\n"
        "Выберите действие:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_vip_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin:vip_list")
async def cb_admin_vip_list(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    db = get_db()
    vips = await db.get_vip_users()
    if not vips:
        text = "👑 <b>Список VIP пуст.</b>"
    else:
        text = "👑 <b>Список VIP пользователей (0% наценки):</b>\n\n"
        for v in vips:
            note_str = f" ({v['note']})" if v.get("note") else ""
            text += f"• ID: <code>{v['user_id']}</code>{note_str} | Добавлен: {v['created_at']}\n"
    
    await callback.message.edit_text(text, reply_markup=get_admin_vip_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin:vip_add")
async def cb_admin_vip_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.set_state(AdminState.waiting_for_vip_id)
    text = (
        "➕ <b>Добавление VIP пользователя</b>\n\n"
        "Отправьте Telegram ID пользователя (или <code>ID Примечание</code>):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(AdminState.waiting_for_vip_id, F.text)
async def process_admin_vip_add(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    parts = message.text.strip().split(maxsplit=1)
    if not parts[0].isdigit():
        await message.answer("⚠️ ID должен быть числовым. Попробуйте еще раз:")
        return

    vip_id = int(parts[0])
    note = parts[1] if len(parts) > 1 else ""
    db = get_db()
    ok = await db.add_vip_user(vip_id, added_by=message.from_user.id, note=note)

    if ok:
        await message.answer(
            f"✅ Пользователь <code>{vip_id}</code> успешно добавлен в VIP!",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer("❌ Ошибка при добавлении в базу данных.")

@router.callback_query(F.data == "admin:vip_remove")
async def cb_admin_vip_remove(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.set_state(AdminState.waiting_for_remove_vip_id)
    text = (
        "➖ <b>Удаление VIP пользователя</b>\n\n"
        "Отправьте Telegram ID пользователя для удаления из VIP:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(AdminState.waiting_for_remove_vip_id, F.text)
async def process_admin_vip_remove(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ ID должен состоять только из цифр:")
        return

    vip_id = int(text)
    db = get_db()
    ok = await db.remove_vip_user(vip_id)

    if ok:
        await message.answer(
            f"✅ Пользователь <code>{vip_id}</code> удален из VIP.",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer("⚠️ Пользователь с таким ID не найден в VIP списке.")

# --- Markup Configuration ---
@router.callback_query(F.data == "admin:markup")
async def cb_admin_markup(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    db = get_db()
    current = await db.get_markup_percent()
    await state.set_state(AdminState.waiting_for_markup)
    text = (
        "📈 <b>Настройка комиссии (наценки)</b>\n\n"
        f"Текущая наценка: <b>{current}%</b>\n\n"
        "<i>Пример: при 30% наценки подарок за 50 звёзд будет стоить 65 звёзд.</i>\n\n"
        "Отправьте новое значение процента (например: <code>25</code> или <code>30</code>):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(AdminState.waiting_for_markup, F.text)
async def process_admin_markup(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 500:
            await message.answer("⚠️ Процент должен быть в диапазоне от 0 до 500.")
            return
        db = get_db()
        await db.set_markup_percent(val)
        await message.answer(
            f"✅ Процент наценки успешно обновлен: <b>{val}%</b>",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Введите корректное число:")

@router.callback_query(F.data == "admin:stars_markup")
async def cb_admin_stars_markup(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    db = get_db()
    current = await db.get_stars_markup_percent()
    await state.set_state(AdminState.waiting_for_stars_markup)
    text = (
        "⚙️ <b>Настройка наценки на звезды</b>\n\n"
        f"Текущая наценка: <b>{current}%</b>\n\n"
        "<i>Эта наценка применяется при продаже звезд через Fragment.</i>\n\n"
        "Отправьте новое значение процента (например: <code>20</code> или <code>25.5</code>):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(AdminState.waiting_for_stars_markup, F.text)
async def process_admin_stars_markup(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 500:
            await message.answer("⚠️ Процент должен быть в диапазоне от 0 до 500.")
            return
        db = get_db()
        await db.set_stars_markup_percent(val)
        await message.answer(
            f"✅ Процент наценки на звезды успешно обновлен: <b>{val}%</b>",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Введите корректное число:")

@router.callback_query(F.data == "admin:evm_fee")
async def cb_admin_evm_fee(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    db = get_db()
    current = await db.get_evm_fee()
    await state.set_state(AdminState.waiting_for_evm_fee)
    text = (
        "⛽️ <b>Настройка EVM комиссии</b>\n\n"
        f"Текущая фиксированная комиссия: <b>${current}</b>\n\n"
        "<i>Эта сумма незаметно прибавляется к счету при оплате в сетях EVM (Polygon, Base) для компенсации расходов на газ при выводе.</i>\n\n"
        "Отправьте новую сумму в долларах/USDC (например: <code>0.10</code> или <code>0.25</code>):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(AdminState.waiting_for_evm_fee, F.text)
async def process_admin_evm_fee(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 10:
            await message.answer("⚠️ Комиссия должна быть в диапазоне от 0 до 10 USDC.")
            return
        db = get_db()
        await db.set_evm_fee(val)
        await message.answer(
            f"✅ Фиксированная EVM комиссия успешно обновлена: <b>${val}</b>",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Введите корректное число:")

# --- Payment Methods Management ---
@router.callback_query(F.data == "admin:payment_methods")
async def cb_admin_payment_methods(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    db = get_db()
    methods_status = await db.get_payment_methods_status()

    status_lines = []
    for key, label in PAYMENT_METHOD_LABELS.items():
        is_on = methods_status.get(key, True)
        badge = "🟢 <b>Включен</b>" if is_on else "🔴 <b>Отключен</b>"
        status_lines.append(f"• <b>{label}:</b> {badge}")
    status_text = "\n".join(status_lines)

    text = (
        "💳 <b>Управление способами оплаты (Покупка Звезд)</b>\n\n"
        "Здесь вы можете включать и выключать способы оплаты криптовалютой.\n"
        "Отключенные способы не будут отображаться пользователям при покупке звёзд.\n\n"
        f"{status_text}\n\n"
        "<i>Нажмите на кнопку ниже, чтобы переключить статус способа оплаты:</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_payment_methods_keyboard(methods_status),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin:toggle_paymethod:"))
async def cb_admin_toggle_paymethod(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    method_key = callback.data.split("admin:toggle_paymethod:")[1]
    if method_key not in PAYMENT_METHOD_LABELS:
        await callback.answer("Неизвестный способ оплаты.", show_alert=True)
        return

    db = get_db()
    new_status = await db.toggle_payment_method(method_key)
    method_label = PAYMENT_METHOD_LABELS[method_key]
    status_str = "включен" if new_status else "отключен"

    methods_status = await db.get_payment_methods_status()
    status_lines = []
    for key, label in PAYMENT_METHOD_LABELS.items():
        is_on = methods_status.get(key, True)
        badge = "🟢 <b>Включен</b>" if is_on else "🔴 <b>Отключен</b>"
        status_lines.append(f"• <b>{label}:</b> {badge}")
    status_text = "\n".join(status_lines)

    text = (
        "💳 <b>Управление способами оплаты (Покупка Звезд)</b>\n\n"
        "Здесь вы можете включать и выключать способы оплаты криптовалютой.\n"
        "Отключенные способы не будут отображаться пользователям при покупке звёзд.\n\n"
        f"{status_text}\n\n"
        "<i>Нажмите на кнопку ниже, чтобы переключить статус способа оплаты:</i>"
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_payment_methods_keyboard(methods_status),
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer(f"{method_label} {status_str}!")

# --- Catalog Management ---

@router.callback_query(F.data == "admin:catalog")
async def cb_admin_catalog(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    text = (
        "📦 <b>Управление каталогом подарков</b>\n\n"
        "Здесь вы можете добавлять популярные скрытые подарки для быстрого выбора в каталоге."
    )
    await callback.message.edit_text(text, reply_markup=get_admin_catalog_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin:cat_list")
async def cb_admin_cat_list(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    db = get_db()
    gifts = await db.get_catalog_gifts()
    if not gifts:
        text = "📦 <b>Каталог пуст.</b>"
    else:
        text = "📦 <b>Список подарков в каталоге:</b>\n\n"
        for g in gifts:
            text += f"• <b>{g['title']}</b> | ID: <code>{g['gift_id']}</code> | {g['stars']} ⭐️\n"

    await callback.message.edit_text(text, reply_markup=get_admin_catalog_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin:cat_add")
async def cb_admin_cat_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.set_state(AdminState.waiting_for_gift_id)
    text = (
        "➕ <b>Добавление подарка в каталог</b>\n\n"
        "Отправьте числовой ID подарка:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(AdminState.waiting_for_gift_id, F.text)
async def process_admin_gift_id(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ ID должен состоять только из цифр:")
        return

    await state.update_data(new_gift_id=int(text))
    await state.set_state(AdminState.waiting_for_gift_title)
    await message.answer("📝 Введите название подарка (например, <i>Exclusive Cake</i>):", parse_mode="HTML")

@router.message(AdminState.waiting_for_gift_title, F.text)
async def process_admin_gift_title(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    await state.update_data(new_gift_title=message.text.strip())
    await state.set_state(AdminState.waiting_for_gift_price)
    await message.answer("💎 Введите базовую стоимость подарка в звёздах (число):")

@router.message(AdminState.waiting_for_gift_price, F.text)
async def process_admin_gift_price(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Стоимость должна быть положительным целым числом:")
        return

    stars = int(text)
    data = await state.get_data()
    gift_id = data["new_gift_id"]
    title = data["new_gift_title"]

    db = get_db()
    ok = await db.add_catalog_gift(gift_id, title, stars)

    if ok:
        await message.answer(
            f"✅ Подарок <b>{title}</b> (ID: <code>{gift_id}</code>, {stars} ⭐️) добавлен в каталог!",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer("❌ Ошибка при сохранении в базу данных.")

@router.callback_query(F.data == "admin:cat_remove")
async def cb_admin_cat_remove(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.set_state(AdminState.waiting_for_remove_gift_id)
    text = (
        "➖ <b>Удаление подарка из каталога</b>\n\n"
        "Отправьте ID подарка, который необходимо удалить:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(AdminState.waiting_for_remove_gift_id, F.text)
async def process_admin_cat_remove(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ ID должен состоять только из цифр:")
        return

    gift_id = int(text)
    db = get_db()
    ok = await db.remove_catalog_gift(gift_id)

    if ok:
        await message.answer(
            f"✅ Подарок <code>{gift_id}</code> удален из каталога.",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer("⚠️ Подарок с таким ID не найден в каталоге.")

# --- Statistics ---
@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    db = get_db()
    stats = await db.get_stats()
    text = (
        "📊 <b>Статистика сервиса</b>\n\n"
        f"👤 <b>Всего пользователей:</b> <code>{stats['users_count']}</code>\n"
        f"👑 <b>VIP пользователей:</b> <code>{stats['vip_count']}</code>\n"
        f"✅ <b>Успешно отправлено подарков:</b> <code>{stats['completed_orders']}</code>\n"
        f"💰 <b>Общая заработанная комиссия:</b> <code>{stats['total_earned_stars']} ⭐️</code>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- Manual Refund Tool ---
@router.callback_query(F.data == "admin:refund")
async def cb_admin_refund(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.set_state(AdminState.waiting_for_refund_data)
    text = (
        "🔄 <b>Ручной возврат звёзд (Refund)</b>\n\n"
        "Отправьте данные для возврата в формате:\n"
        "<code>USER_ID CHARGE_ID</code>\n\n"
        "<i>Пример: <code>123456789 ch_abc123xyz</code></i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(AdminState.waiting_for_refund_data, F.text)
async def process_admin_refund(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("⚠️ Неверный формат. Введите: <code>USER_ID CHARGE_ID</code>", parse_mode="HTML")
        return

    user_id = int(parts[0])
    charge_id = parts[1]

    ok, r_msg = await PaymentService.refund_stars(
        bot=bot,
        user_id=user_id,
        charge_id=charge_id,
        reason="Ручной возврат администратором"
    )

    if ok:
        await message.answer(
            f"✅ <b>Возврат успешно выполнен:</b> {r_msg}",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer(
            f"❌ <b>Ошибка возврата:</b> {r_msg}",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )


# ==========================================
# PARTNER MANAGEMENT (ADMIN)
# ==========================================

@router.callback_query(F.data == "admin:noop")
async def cb_admin_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("admin:partners"))
async def cb_admin_partners_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin_filter(callback):
        return
    await state.clear()

    page = 1
    parts = callback.data.split(":")
    if len(parts) >= 3 and parts[2].isdigit():
        page = int(parts[2])

    db = get_db()
    partners = await db.get_all_partners()
    promo_links = await db.get_all_promo_links()

    total_count = len(partners)
    per_page = 8
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages)) if total_count > 0 else 1

    page_header = f" <i>(Стр. {page}/{total_pages})</i>" if total_pages > 1 else ""
    text = (
        f"🤝 <b>Управление партнерами и промо-ссылками</b>{page_header}\n\n"
        f"🔗 <b>Создано промо-ссылок:</b> <b>{len(promo_links)}</b>\n"
        f"👥 <b>Всего партнеров / участников:</b> <b>{len(partners)}</b>\n\n"
        "• Для создания ссылок и настройки наценок (скидок) нажмите <b>«🔗 Управление промо-ссылками»</b>.\n"
        "• Выберите партнера из списка ниже для просмотра статистики и настройки условий:"
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_partners_menu_keyboard(partners, page=page, per_page=per_page),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=get_admin_partners_menu_keyboard(partners, page=page, per_page=per_page),
            parse_mode="HTML"
        )
    await callback.answer()


# ==========================================
# PROMO LINKS MANAGEMENT
# ==========================================

@router.callback_query(F.data == "admin:promo_links_list")
async def cb_admin_promo_links_list(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin_filter(callback):
        return
    await state.clear()
    db = get_db()
    promo_links = await db.get_all_promo_links()

    text = (
        "🔗 <b>Управление рекламными промо-ссылками</b>\n\n"
        "Здесь вы можете создавать ссылки со своими тегами, настраивать индивидуальные проценты наценок на подарки и звёзды, "
        "срок партнерки, а также отслеживать количество переходов.\n\n"
        f"Всего ссылок: <b>{len(promo_links)}</b>\n\n"
        "Выберите промо-ссылку для настройки или создайте новую:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_promo_links_keyboard(promo_links), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:promo_card:"))
async def cb_admin_promo_card(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin_filter(callback):
        return
    await state.clear()
    code = callback.data.split(":", 2)[2]
    db = get_db()
    promo = await db.get_promo_link(code)
    if not promo:
        await callback.answer("⚠️ Промо-ссылка не найдена!", show_alert=True)
        await cb_admin_promo_links_list(callback, state, bot)
        return

    bot_user = await bot.get_me()
    bot_username = bot_user.username or ""
    link_url = f"https://t.me/{bot_username}?start={promo['code']}"

    status_str = "🟢 <b>Активна</b>" if promo.get("is_active", 1) else "🔴 <b>Отключена</b>"
    p_gift = float(promo.get("gift_markup_percent", 15.0))
    p_stars = float(promo.get("stars_markup_percent", 10.0))
    p_gift_str = f"{int(p_gift)}" if p_gift.is_integer() else f"{p_gift}"
    p_stars_str = f"{int(p_stars)}" if p_stars.is_integer() else f"{p_stars}"

    text = (
        f"🔗 <b>Промо-ссылка: {promo['name']}</b>\n\n"
        f"📌 <b>Ссылка:</b> <code>{link_url}</code>\n"
        f"🏷️ <b>Код (start-параметр):</b> <code>{promo['code']}</code>\n"
        f"🔘 <b>Статус:</b> {status_str}\n\n"
        f"🎁 <b>Наценка на подарки:</b> <code>{p_gift_str}%</code>\n"
        f"⭐️ <b>Наценка на звёзды:</b> <code>{p_stars_str}%</code>\n"
        f"⏳ <b>Срок партнерки:</b> <code>{promo.get('duration_days', 30)} дн.</code>\n"
        f"👥 <b>Количество активаций:</b> <b>{promo.get('activations_count', 0)}</b>\n\n"
        "<i>Пользователи, перешедшие по этой ссылке, получают указанные выше наценки и партнерский статус.</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_promo_card_keyboard(promo['code'], is_active=bool(promo.get("is_active", 1))),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:promo_toggle:"))
async def cb_admin_promo_toggle(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin_filter(callback):
        return
    code = callback.data.split(":", 2)[2]
    db = get_db()
    promo = await db.get_promo_link(code)
    if promo:
        new_status = 0 if promo.get("is_active", 1) else 1
        await db.update_promo_link(code, is_active=new_status)
        await callback.answer("Ссылка активирована!" if new_status else "Ссылка отключена!")
    await cb_admin_promo_card(callback, state, bot)


@router.callback_query(F.data.startswith("admin:promo_delete:"))
async def cb_admin_promo_delete(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin_filter(callback):
        return
    code = callback.data.split(":", 2)[2]
    db = get_db()
    all_links = await db.get_all_promo_links()
    if len(all_links) <= 1:
        await callback.answer("⚠️ Нельзя удалить единственную промо-ссылку!", show_alert=True)
        return
    await db.delete_promo_link(code)
    await callback.answer("🗑️ Промо-ссылка успешно удалена!", show_alert=True)
    await cb_admin_promo_links_list(callback, state, bot)


# --- Create Promo Link FSM ---

@router.callback_query(F.data == "admin:promo_create")
async def cb_admin_promo_create_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.clear()
    await state.set_state(AdminPromoCreateState.waiting_for_code)
    text = (
        "➕ <b>Создание новой промо-ссылки (Шаг 1/5)</b>\n\n"
        "Введите уникальный <b>промо-тег</b> (параметр <code>start</code> в ссылке):\n"
        "<i>Разрешены латинские буквы, цифры, _ и - (от 2 до 64 символов).\n"
        "Например: <code>tg_channel</code>, <code>promo_autumn</code>, <code>forum2</code></i>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_promo_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminPromoCreateState.waiting_for_code, F.text)
async def process_promo_create_code(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    code = message.text.strip().lower()
    import re
    if not re.match(r"^[a-zA-Z0-9_-]{2,64}$", code):
        await message.answer(
            "⚠️ Некорректный формат тега. Разрешены только латинские буквы, цифры, _ и - (от 2 до 64 символов).\nПопробуйте еще раз:",
            reply_markup=get_admin_promo_cancel_keyboard()
        )
        return

    db = get_db()
    existing = await db.get_promo_link(code)
    if existing:
        await message.answer(
            f"⚠️ Промо-ссылка с тегом <code>{code}</code> уже существует. Введите другой тег:",
            reply_markup=get_admin_promo_cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.update_data(promo_code=code)
    await state.set_state(AdminPromoCreateState.waiting_for_name)
    await message.answer(
        f"✅ Тег: <code>{code}</code>\n\n"
        "➕ <b>(Шаг 2/5)</b> Введите <b>название</b> для этой промо-ссылки (для админки):\n"
        "<i>Например: <code>Реклама в канале @CryptoGifts</code> или <code>Акция на форуме Lolz</code></i>",
        reply_markup=get_admin_promo_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminPromoCreateState.waiting_for_name, F.text)
async def process_promo_create_name(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    name = message.text.strip()
    if len(name) < 1 or len(name) > 100:
        await message.answer(
            "⚠️ Название должно быть от 1 до 100 символов. Попробуйте еще раз:",
            reply_markup=get_admin_promo_cancel_keyboard()
        )
        return

    await state.update_data(promo_name=name)
    await state.set_state(AdminPromoCreateState.waiting_for_gift_markup)
    await message.answer(
        f"✅ Название: <b>{name}</b>\n\n"
        "➕ <b>(Шаг 3/5)</b> Введите процент <b>наценки на подарки</b>:\n"
        "<i>Стандартная наценка в боте — 30%. Введите число, например: <code>15</code> или <code>10.5</code></i>",
        reply_markup=get_admin_promo_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminPromoCreateState.waiting_for_gift_markup, F.text)
async def process_promo_create_gift_markup(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 500:
            raise ValueError()
    except ValueError:
        await message.answer(
            "⚠️ Введите корректное число от 0 до 500 (например: <code>15</code> или <code>12.5</code>):",
            reply_markup=get_admin_promo_cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.update_data(promo_gift_markup=val)
    await state.set_state(AdminPromoCreateState.waiting_for_stars_markup)
    await message.answer(
        f"✅ Наценка на подарки: <b>{val}%</b>\n\n"
        "➕ <b>(Шаг 4/5)</b> Введите процент <b>наценки на звёзды</b>:\n"
        "<i>Стандартная наценка в боте — 20%. Введите число, например: <code>10</code> или <code>5</code></i>",
        reply_markup=get_admin_promo_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminPromoCreateState.waiting_for_stars_markup, F.text)
async def process_promo_create_stars_markup(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 500:
            raise ValueError()
    except ValueError:
        await message.answer(
            "⚠️ Введите корректное число от 0 до 500 (например: <code>10</code> или <code>7.5</code>):",
            reply_markup=get_admin_promo_cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.update_data(promo_stars_markup=val)
    await state.set_state(AdminPromoCreateState.waiting_for_duration)
    await message.answer(
        f"✅ Наценка на звёзды: <b>{val}%</b>\n\n"
        "➕ <b>(Шаг 5/5)</b> Введите <b>срок действия партнерки</b> (в днях):\n"
        "<i>Например: <code>30</code> (1 месяц), <code>14</code> (2 недели), <code>60</code> (2 месяца)</i>",
        reply_markup=get_admin_promo_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminPromoCreateState.waiting_for_duration, F.text)
async def process_promo_create_duration(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    try:
        val = int(message.text.strip())
        if val < 1 or val > 3650:
            raise ValueError()
    except ValueError:
        await message.answer(
            "⚠️ Введите целое число дней от 1 до 3650 (например: <code>30</code>):",
            reply_markup=get_admin_promo_cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    await state.clear()

    db = get_db()
    code = data["promo_code"]
    name = data["promo_name"]
    gift_markup = data["promo_gift_markup"]
    stars_markup = data["promo_stars_markup"]
    duration = val

    created = await db.create_promo_link(
        code=code,
        name=name,
        gift_markup=gift_markup,
        stars_markup=stars_markup,
        duration_days=duration
    )

    bot_user = await bot.get_me()
    bot_username = bot_user.username or ""
    link_url = f"https://t.me/{bot_username}?start={code}"

    if created:
        await message.answer(
            f"🎉 <b>Промо-ссылка успешно создана!</b>\n\n"
            f"🔗 <b>Ссылка:</b> <code>{link_url}</code>\n"
            f"📝 <b>Название:</b> {name}\n"
            f"🎁 <b>Наценка на подарки:</b> {gift_markup}%\n"
            f"⭐️ <b>Наценка на звёзды:</b> {stars_markup}%\n"
            f"⏳ <b>Срок:</b> {duration} дн.\n\n"
            "Вы можете поделиться этой ссылкой для привлечения пользователей.",
            reply_markup=get_admin_promo_card_keyboard(code, is_active=True),
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ Ошибка при создании промо-ссылки в базе данных.", reply_markup=get_admin_promo_cancel_keyboard())


# --- Edit Existing Promo Link Parameters ---

@router.callback_query(F.data.startswith("admin:promo_edit_gift:"))
async def cb_admin_promo_edit_gift(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    code = callback.data.split(":", 2)[2]
    db = get_db()
    promo = await db.get_promo_link(code)
    if not promo:
        await callback.answer("⚠️ Ссылка не найдена!", show_alert=True)
        return

    await state.set_state(AdminPromoEditState.waiting_for_gift_markup)
    await state.update_data(edit_promo_code=code)
    text = (
        f"🎁 <b>Изменение наценки на подарки</b> для ссылки <code>{code}</code>\n\n"
        f"Текущее значение: <b>{promo.get('gift_markup_percent', 15.0)}%</b>\n\n"
        "Введите новый процент наценки на подарки (число от 0 до 500):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_promo_cancel_keyboard(code), parse_mode="HTML")
    await callback.answer()


@router.message(AdminPromoEditState.waiting_for_gift_markup, F.text)
async def process_admin_promo_edit_gift(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 500:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Введите число от 0 до 500:")
        return

    data = await state.get_data()
    code = data.get("edit_promo_code")
    await state.clear()

    db = get_db()
    await db.update_promo_link(code, gift_markup=val)
    promo = await db.get_promo_link(code)

    bot_user = await bot.get_me()
    bot_username = bot_user.username or ""
    link_url = f"https://t.me/{bot_username}?start={promo['code']}"

    await message.answer(
        f"✅ Наценка на подарки для <code>{code}</code> обновлена на <b>{val}%</b>!\n\n"
        f"🔗 Ссылка: <code>{link_url}</code>",
        reply_markup=get_admin_promo_card_keyboard(code, is_active=bool(promo.get("is_active", 1))),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin:promo_edit_stars:"))
async def cb_admin_promo_edit_stars(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    code = callback.data.split(":", 2)[2]
    db = get_db()
    promo = await db.get_promo_link(code)
    if not promo:
        await callback.answer("⚠️ Ссылка не найдена!", show_alert=True)
        return

    await state.set_state(AdminPromoEditState.waiting_for_stars_markup)
    await state.update_data(edit_promo_code=code)
    text = (
        f"⭐️ <b>Изменение наценки на звёзды</b> для ссылки <code>{code}</code>\n\n"
        f"Текущее значение: <b>{promo.get('stars_markup_percent', 10.0)}%</b>\n\n"
        "Введите новый процент наценки на звёзды (число от 0 до 500):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_promo_cancel_keyboard(code), parse_mode="HTML")
    await callback.answer()


@router.message(AdminPromoEditState.waiting_for_stars_markup, F.text)
async def process_admin_promo_edit_stars(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 500:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Введите число от 0 до 500:")
        return

    data = await state.get_data()
    code = data.get("edit_promo_code")
    await state.clear()

    db = get_db()
    await db.update_promo_link(code, stars_markup=val)
    promo = await db.get_promo_link(code)

    bot_user = await bot.get_me()
    bot_username = bot_user.username or ""
    link_url = f"https://t.me/{bot_username}?start={promo['code']}"

    await message.answer(
        f"✅ Наценка на звёзды для <code>{code}</code> обновлена на <b>{val}%</b>!\n\n"
        f"🔗 Ссылка: <code>{link_url}</code>",
        reply_markup=get_admin_promo_card_keyboard(code, is_active=bool(promo.get("is_active", 1))),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin:promo_edit_days:"))
async def cb_admin_promo_edit_days(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    code = callback.data.split(":", 2)[2]
    db = get_db()
    promo = await db.get_promo_link(code)
    if not promo:
        await callback.answer("⚠️ Ссылка не найдена!", show_alert=True)
        return

    await state.set_state(AdminPromoEditState.waiting_for_duration)
    await state.update_data(edit_promo_code=code)
    text = (
        f"⏳ <b>Изменение срока действия</b> для ссылки <code>{code}</code>\n\n"
        f"Текущее значение: <b>{promo.get('duration_days', 30)} дней</b>\n\n"
        "Введите новый срок действия партнерки в днях (число от 1 до 3650):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_promo_cancel_keyboard(code), parse_mode="HTML")
    await callback.answer()


@router.message(AdminPromoEditState.waiting_for_duration, F.text)
async def process_admin_promo_edit_days(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    try:
        val = int(message.text.strip())
        if val < 1 or val > 3650:
            raise ValueError()
    except ValueError:
        await message.answer("⚠️ Введите целое число дней от 1 до 3650:")
        return

    data = await state.get_data()
    code = data.get("edit_promo_code")
    await state.clear()

    db = get_db()
    await db.update_promo_link(code, duration_days=val)
    promo = await db.get_promo_link(code)

    bot_user = await bot.get_me()
    bot_username = bot_user.username or ""
    link_url = f"https://t.me/{bot_username}?start={promo['code']}"

    await message.answer(
        f"✅ Срок действия партнерки для <code>{code}</code> обновлен на <b>{val} дн.</b>!\n\n"
        f"🔗 Ссылка: <code>{link_url}</code>",
        reply_markup=get_admin_promo_card_keyboard(code, is_active=bool(promo.get("is_active", 1))),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin:part_search")
async def cb_admin_part_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.set_state(AdminPartnerState.waiting_for_partner_search)
    text = (
        "🔍 <b>Поиск партнера</b>\n\n"
        "Введите числовой <b>User ID</b> или <b>@username</b> пользователя:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminPartnerState.waiting_for_partner_search, F.text)
async def process_admin_part_search(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    query = message.text.strip().replace("@", "")
    db = get_db()
    
    target_id = None
    if query.isdigit():
        target_id = int(query)
    else:
        # Search by username in users
        async with aiosqlite_connect_db() as raw_db:
            async with raw_db.execute("SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)", (query,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    target_id = row[0]

    if not target_id:
        await message.answer("⚠️ Пользователь не найден. Попробуйте еще раз:", reply_markup=get_admin_back_keyboard())
        return

    await state.clear()
    await show_admin_partner_card(message, target_id)


def aiosqlite_connect_db():
    import aiosqlite
    from config import DB_PATH
    return aiosqlite.connect(DB_PATH)


async def show_admin_partner_card(event: Message | CallbackQuery, partner_id: int):
    db = get_db()
    stats = await db.get_partner_stats(partner_id)
    user_label = f"@{stats['username']}" if stats.get("username") else f"{stats.get('first_name', 'User')}"

    status_str = "🟢 Активен" if (stats["is_partner"] and not stats["is_expired"]) else ("⌛️ Истек" if stats["is_expired"] else "⚪️ Не партнер")
    hold_str = stats["hold_left_str"] if stats["hold_active"] else "Нет активного холда"

    source_promo = stats.get("invited_by_promo")
    referrer_id = stats.get("referrer_id")
    if source_promo:
        p_info = await db.get_promo_link(source_promo)
        p_name = p_info["name"] if p_info else "Промо-акция"
        source_str = f"🔗 <b>Источник перехода:</b> Промо-ссылка «<code>{source_promo}</code>» ({p_name})\n"
    elif referrer_id:
        async with aiosqlite_connect_db() as raw_db:
            async with raw_db.execute("SELECT username, first_name FROM users WHERE user_id = ?", (referrer_id,)) as cur:
                ref_user = await cur.fetchone()
        if ref_user and ref_user[0]:
            ref_label = f"@{ref_user[0]} (ID: <code>{referrer_id}</code>)"
        elif ref_user and ref_user[1]:
            ref_label = f"{ref_user[1]} (ID: <code>{referrer_id}</code>)"
        else:
            ref_label = f"ID <code>{referrer_id}</code>"
        source_str = f"👥 <b>Источник перехода:</b> Реферал от {ref_label}\n"
    else:
        source_str = "🌐 <b>Источник перехода:</b> Прямой вход (без ссылки)\n"

    text = (
        f"👤 <b>Партнер:</b> {user_label} (ID: <code>{partner_id}</code>)\n\n"
        f"📊 <b>Статус программы:</b> {status_str}\n"
        f"{source_str}"
        f"⏳ <b>Срок действия:</b> <code>{stats['time_left_str']}</code> (до {str(stats['partner_expires_at'])[:16] if stats['partner_expires_at'] else '—'})\n"
        f"🎁 <b>Наценка на подарки:</b> <code>{stats['gift_markup_percent']}%</code>\n"
        f"⭐️ <b>Наценка на звезды:</b> <code>{stats['stars_markup_percent']}%</code>\n\n"
        f"💼 <b>Партнерский баланс:</b> <b>{stats['partner_balance']} ⭐️</b>\n"
        f"⏳ <b>Холд:</b> {hold_str}\n\n"
        "👥 <b>Реферальная статистика:</b>\n"
        f"• Всего приглашено: <b>{stats['total_referrals']}</b> чел.\n"
        f"• Активных рефералов (5+ покупок): <b>{stats['active_referrals_5plus']}</b> чел.\n"
        f"• Всего заработано: <b>{stats['total_earned_stars']} ⭐️</b>"
    )

    reply_markup = get_admin_partner_card_keyboard(partner_id)
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:part_card:"))
async def cb_admin_part_card(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.clear()
    partner_id = int(callback.data.split(":")[2])
    await show_admin_partner_card(callback, partner_id)


@router.callback_query(F.data.startswith("admin:part_gift_markup:"))
async def cb_admin_part_gift_markup(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    partner_id = int(callback.data.split(":")[2])
    await state.set_state(AdminPartnerState.waiting_for_gift_markup)
    await state.update_data(target_partner_id=partner_id)

    await callback.message.edit_text(
        f"🎁 Введите <b>новую наценку на подарки (%)</b> для партнера <code>{partner_id}</code>:\n\n"
        "<i>Например: <code>15.0</code> или <code>20</code></i>",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminPartnerState.waiting_for_gift_markup, F.text)
async def process_admin_part_gift_markup(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    data = await state.get_data()
    partner_id = data.get("target_partner_id")
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 100:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректное число от 0 до 100.")
        return

    db = get_db()
    await db.update_partner_settings(partner_id, gift_markup=val)
    await state.clear()
    await message.answer(f"✅ Наценка на подарки для партнера <code>{partner_id}</code> установлена на <b>{val}%</b>!")
    await show_admin_partner_card(message, partner_id)


@router.callback_query(F.data.startswith("admin:part_stars_markup:"))
async def cb_admin_part_stars_markup(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    partner_id = int(callback.data.split(":")[2])
    await state.set_state(AdminPartnerState.waiting_for_stars_markup)
    await state.update_data(target_partner_id=partner_id)

    await callback.message.edit_text(
        f"⭐️ Введите <b>новую наценку на звезды (%)</b> для партнера <code>{partner_id}</code>:\n\n"
        "<i>Например: <code>10.0</code> или <code>15</code></i>",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminPartnerState.waiting_for_stars_markup, F.text)
async def process_admin_part_stars_markup(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    data = await state.get_data()
    partner_id = data.get("target_partner_id")
    try:
        val = float(message.text.strip().replace(",", "."))
        if val < 0 or val > 100:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректное число от 0 до 100.")
        return

    db = get_db()
    await db.update_partner_settings(partner_id, stars_markup=val)
    await state.clear()
    await message.answer(f"✅ Наценка на звезды для партнера <code>{partner_id}</code> установлена на <b>{val}%</b>!")
    await show_admin_partner_card(message, partner_id)


@router.callback_query(F.data.startswith("admin:part_extend:"))
async def cb_admin_part_extend(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    partner_id = int(callback.data.split(":")[2])
    text = f"⏳ <b>Продление срока партнерской программы</b> для ID <code>{partner_id}</code>:\n\nВыберите срок:"
    await callback.message.edit_text(text, reply_markup=get_admin_partner_extend_keyboard(partner_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:part_add_days:"))
async def cb_admin_part_add_days(callback: CallbackQuery, bot: Bot):
    if not is_admin_filter(callback):
        return
    parts = callback.data.split(":")
    partner_id = int(parts[2])
    days_to_add = int(parts[3])

    db = get_db()
    user_info = await db.get_user(partner_id)
    cur_exp = user_info.get("partner_expires_at") if user_info else None

    now = datetime.datetime.now()
    if cur_exp:
        try:
            cur_dt = datetime.datetime.fromisoformat(str(cur_exp).replace("Z", ""))
            base_dt = max(now, cur_dt)
        except Exception:
            base_dt = now
    else:
        base_dt = now

    new_exp = base_dt + datetime.timedelta(days=days_to_add)
    await db.update_partner_settings(partner_id, partner_expires_at=new_exp, is_partner=1)

    try:
        await bot.send_message(
            chat_id=partner_id,
            text=(
                f"🎉 <b>Срок вашей партнерской программы продлен на {days_to_add} дн.!</b>\n\n"
                f"📅 Действует до: <b>{new_exp.strftime('%d.%m.%Y %H:%M')}</b>"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer(f"Продлено на {days_to_add} дней!")
    await show_admin_partner_card(callback, partner_id)


@router.callback_query(F.data.startswith("admin:part_custom_days:"))
async def cb_admin_part_custom_days(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    partner_id = int(callback.data.split(":")[2])
    await state.set_state(AdminPartnerState.waiting_for_custom_days)
    await state.update_data(target_partner_id=partner_id)

    await callback.message.edit_text(
        f"✍️ Введите <b>количество дней</b> для продления программы партнера <code>{partner_id}</code>:",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminPartnerState.waiting_for_custom_days, F.text)
async def process_admin_part_custom_days(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    data = await state.get_data()
    partner_id = data.get("target_partner_id")

    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("⚠️ Введите положительное целое число дней.")
        return

    days_to_add = int(message.text.strip())
    db = get_db()
    user_info = await db.get_user(partner_id)
    cur_exp = user_info.get("partner_expires_at") if user_info else None

    now = datetime.datetime.now()
    if cur_exp:
        try:
            cur_dt = datetime.datetime.fromisoformat(str(cur_exp).replace("Z", ""))
            base_dt = max(now, cur_dt)
        except Exception:
            base_dt = now
    else:
        base_dt = now

    new_exp = base_dt + datetime.timedelta(days=days_to_add)
    await db.update_partner_settings(partner_id, partner_expires_at=new_exp, is_partner=1)
    await state.clear()

    try:
        await bot.send_message(
            chat_id=partner_id,
            text=(
                f"🎉 <b>Срок вашей партнерской программы продлен на {days_to_add} дн.!</b>\n\n"
                f"📅 Действует до: <b>{new_exp.strftime('%d.%m.%Y %H:%M')}</b>"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await message.answer(f"✅ Программа продлена на {days_to_add} дней (до {new_exp.strftime('%d.%m.%Y %H:%M')})!")
    await show_admin_partner_card(message, partner_id)


@router.callback_query(F.data.startswith("admin:part_refs:"))
async def cb_admin_part_refs(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    partner_id = int(callback.data.split(":")[2])
    db = get_db()
    stats = await db.get_partner_stats(partner_id)
    referrals = stats.get("referrals", [])

    if not referrals:
        text = f"📋 У партнера <code>{partner_id}</code> пока нет рефералов."
    else:
        lines = []
        for i, ref in enumerate(referrals[:40], 1):
            name = f"@{ref['username']}" if ref.get("username") else f"ID {ref['user_id']}"
            orders_cnt = ref.get("total_orders", 0)
            badge = " 🔥 (5+)" if orders_cnt >= 5 else ""
            lines.append(f"{i}. {name} — {orders_cnt} покупок{badge}")
        
        text = (
            f"📋 <b>Рефералы партнера <code>{partner_id}</code> ({len(referrals)} чел.):</b>\n\n"
            + "\n".join(lines)
        )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_partner_card_keyboard(partner_id),
        parse_mode="HTML"
    )
    await callback.answer()


# ==========================================
# PARTNER APPLICATIONS (ADMIN)
# ==========================================

@router.callback_query(F.data == "admin:applications")
async def cb_admin_applications(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.clear()
    db = get_db()
    apps = await db.get_pending_applications()

    if not apps:
        await callback.message.edit_text(
            "📬 <b>Заявки партнеров</b>\n\nНет активных заявок на рассмотрении.",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    text = f"📬 <b>Заявки партнеров (ожидают решения: {len(apps)}):</b>\n\nВыберите заявку для просмотра:"
    await callback.message.edit_text(text, reply_markup=get_admin_applications_keyboard(apps), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:app_card:"))
async def cb_admin_app_card(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.clear()
    app_id = int(callback.data.split(":")[2])
    db = get_db()
    app = await db.get_application_by_id(app_id)
    if not app:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    stats = await db.get_partner_stats(app["user_id"])
    user_label = f"@{stats['username']}" if stats.get("username") else f"{stats.get('first_name', 'User')}"
    app_type_str = "🔄 ПРОДЛЕНИЕ программы" if app["type"] == "renewal" else "📝 ВСТУПЛЕНИЕ в программу"

    text = (
        f"📌 <b>Заявка #{app_id}</b>\n\n"
        f"Тип: <b>{app_type_str}</b>\n"
        f"👤 Пользователь: {user_label} (ID: <code>{app['user_id']}</code>)\n"
        f"💬 <b>Сообщение/комментарий:</b>\n<i>{app.get('note') or 'Без комментария'}</i>\n\n"
        "📊 <b>Текущая статистика:</b>\n"
        f"• Всего рефералов: <b>{stats['total_referrals']}</b> чел.\n"
        f"• Активных (5+ покупок): <b>{stats['active_referrals_5plus']}</b> чел.\n"
        f"• Заработано: <b>{stats['total_earned_stars']} ⭐️</b>\n"
        f"• Баланс: <b>{stats['partner_balance']} ⭐️</b>\n"
        f"• Дата создания заявки: <code>{app['created_at']}</code>"
    )

    await callback.message.edit_text(text, reply_markup=get_admin_app_card_keyboard(app_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:app_approve:"))
async def cb_admin_app_approve(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return
    app_id = int(callback.data.split(":")[2])
    text = (
        f"✅ <b>Одобрение заявки #{app_id}</b>\n\n"
        "Выберите <b>срок действия</b> партнерской программы для пользователя:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_duration_choice_keyboard(app_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:app_dur:"))
async def cb_admin_app_dur(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    parts = callback.data.split(":")
    app_id = int(parts[2])
    duration_days = int(parts[3])

    await state.set_state(AdminApplicationDecisionState.waiting_for_comment)
    await state.update_data(decision_app_id=app_id, duration_days=duration_days)

    text = (
        f"✅ Срок программы: <b>{duration_days} дней</b>.\n\n"
        "Введите <b>комментарий для партнера</b> (или отправьте <code>-</code> чтобы отправить без комментария):"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:app_dur_custom:"))
async def cb_admin_app_dur_custom(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    app_id = int(callback.data.split(":")[2])
    await state.set_state(AdminApplicationDecisionState.waiting_for_duration_days)
    await state.update_data(decision_app_id=app_id)

    await callback.message.edit_text(
        "✍️ Введите <b>количество дней</b> для партнерской программы:",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminApplicationDecisionState.waiting_for_duration_days, F.text)
async def process_app_dur_custom_input(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("⚠️ Введите положительное число дней.")
        return

    duration_days = int(message.text.strip())
    await state.update_data(duration_days=duration_days)
    await state.set_state(AdminApplicationDecisionState.waiting_for_comment)

    await message.answer(
        f"✅ Срок: <b>{duration_days} дней</b>.\n\n"
        "Введите <b>комментарий для партнера</b> (или отправьте <code>-</code>):"
    )


@router.message(AdminApplicationDecisionState.waiting_for_comment, F.text)
async def process_app_approve_comment(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    data = await state.get_data()
    app_id = data.get("decision_app_id")
    duration_days = data.get("duration_days", 30)
    comment = message.text.strip()
    if comment == "-":
        comment = "Ваша заявка успешно одобрена. Желаем успешной работы!"

    db = get_db()
    app = await db.get_application_by_id(app_id)
    if not app:
        await message.answer("⚠️ Заявка не найдена.")
        await state.clear()
        return

    user_id = app["user_id"]
    exp_dt = await db.activate_partner(user_id=user_id, days=duration_days, gift_markup=15.0, stars_markup=10.0)
    await db.update_application_status(app_id, "approved")
    await state.clear()

    # Notify partner
    try:
        user_info = await db.get_user(user_id)
        gift_m = user_info.get("gift_markup_percent", 15.0) if user_info else 15.0
        stars_m = user_info.get("stars_markup_percent", 10.0) if user_info else 10.0
        partner_notify_text = (
            "🎉 <b>Ваша заявка на партнерскую программу успешно одобрена!</b>\n\n"
            f"⏳ <b>Срок программы:</b> {duration_days} дн. (до <b>{exp_dt.strftime('%d.%m.%Y %H:%M')}</b>)\n"
            f"🎁 <b>Ваша наценка на подарки:</b> <code>{gift_m}%</code>\n"
            f"⭐️ <b>Ваша наценка на звезды:</b> <code>{stars_m}%</code>\n"
            f"💬 <b>Сообщение от администрации:</b>\n<i>{comment}</i>\n\n"
            "Перейдите в раздел «🤝 Партнерская программа», чтобы получить вашу персональную реферальную ссылку!"
        )
        await bot.send_message(chat_id=user_id, text=partner_notify_text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Could not notify partner {user_id}: {e}")

    await message.answer(
        f"✅ <b>Заявка #{app_id} одобрена!</b>\nПартнер ID <code>{user_id}</code> активирован на {duration_days} дней.",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin:app_reject:"))
async def cb_admin_app_reject(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    app_id = int(callback.data.split(":")[2])
    await state.set_state(AdminApplicationDecisionState.waiting_for_reject_reason)
    await state.update_data(decision_app_id=app_id)

    await callback.message.edit_text(
        f"❌ Введите <b>причину отклонения</b> заявки #{app_id}:",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminApplicationDecisionState.waiting_for_reject_reason, F.text)
async def process_app_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    data = await state.get_data()
    app_id = data.get("decision_app_id")
    reason = message.text.strip()

    db = get_db()
    app = await db.get_application_by_id(app_id)
    if not app:
        await message.answer("⚠️ Заявка не найдена.")
        await state.clear()
        return

    user_id = app["user_id"]
    await db.update_application_status(app_id, "rejected")
    await state.clear()

    try:
        partner_notify_text = (
            "❌ <b>Ваша заявка на партнерскую программу была отклонена.</b>\n\n"
            f"💬 <b>Причина / комментарий администрации:</b>\n<i>{reason}</i>"
        )
        await bot.send_message(chat_id=user_id, text=partner_notify_text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Could not notify user {user_id}: {e}")

    await message.answer(
        f"❌ <b>Заявка #{app_id} отклонена.</b> Пользователь получил уведомление.",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )


# ==========================================
# WITHDRAWALS MANAGEMENT (ADMIN)
# ==========================================

@router.callback_query(F.data == "admin:withdrawals")
async def cb_admin_withdrawals(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.clear()
    db = get_db()
    wds = await db.get_pending_withdrawals()

    if not wds:
        await callback.message.edit_text(
            "💸 <b>Заявки на вывод средств</b>\n\nНет активных заявок на вывод.",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    text = f"💸 <b>Заявки на вывод средств (ожидают: {len(wds)}):</b>\n\nВыберите заявку:"
    await callback.message.edit_text(text, reply_markup=get_admin_withdrawals_keyboard(wds), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:wd_card:"))
async def cb_admin_wd_card(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.clear()
    wd_id = int(callback.data.split(":")[2])
    db = get_db()
    wd = await db.get_withdrawal_request(wd_id)
    if not wd:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    user_info = await db.get_user(wd["user_id"])
    user_label = f"@{user_info['username']}" if user_info and user_info.get("username") else f"ID {wd['user_id']}"
    memo_str = f"<code>{wd['memo']}</code>" if wd.get("memo") else "<i>Без memo</i>"

    text = (
        f"💸 <b>Заявка на вывод #{wd_id}</b>\n\n"
        f"👤 Партнер: {user_label} (ID: <code>{wd['user_id']}</code>)\n"
        f"⭐️ <b>Сумма к выплате:</b> <b>{wd['amount_stars']} ⭐️</b>\n"
        f"💎 <b>TON Адрес:</b> <code>{wd['ton_address']}</code>\n"
        f"📝 <b>Memo:</b> {memo_str}\n"
        f"📅 Создана: <code>{wd['created_at']}</code>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_withdrawal_card_keyboard(wd_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:wd_approve:"))
async def cb_admin_wd_approve(callback: CallbackQuery, bot: Bot):
    if not is_admin_filter(callback):
        return
    wd_id = int(callback.data.split(":")[2])
    db = get_db()
    wd = await db.get_withdrawal_request(wd_id)
    if not wd:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    await db.update_withdrawal_status(wd_id, "completed", "Выплачено администратором")

    try:
        await bot.send_message(
            chat_id=wd["user_id"],
            text=(
                f"🎉 <b>Ваша выплата по заявке #{wd_id} успешно выполнена!</b>\n\n"
                f"⭐️ Сумма: <b>{wd['amount_stars']} ⭐️</b>\n"
                f"💎 Адрес: <code>{wd['ton_address']}</code>\n\n"
                "Средства отправлены на ваш кошелек. Спасибо за сотрудничество!"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Could not notify user {wd['user_id']}: {e}")

    await callback.message.edit_text(
        f"✅ <b>Заявка #{wd_id} помечена как выполненная!</b>\nПартнер получил уведомление.",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("Выплата подтверждена!")


@router.callback_query(F.data.startswith("admin:wd_reject:"))
async def cb_admin_wd_reject(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    wd_id = int(callback.data.split(":")[2])
    await state.set_state(AdminWithdrawalDecisionState.waiting_for_reject_reason)
    await state.update_data(decision_wd_id=wd_id)

    await callback.message.edit_text(
        f"❌ Введите <b>причину отклонения</b> заявки на вывод #{wd_id}:\n\n"
        "<i>Звёзды будут автоматически возвращены на баланс партнера.</i>",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminWithdrawalDecisionState.waiting_for_reject_reason, F.text)
async def process_admin_wd_reject(message: Message, state: FSMContext, bot: Bot):
    if not is_admin_filter(message):
        return
    data = await state.get_data()
    wd_id = data.get("decision_wd_id")
    reason = message.text.strip()

    db = get_db()
    wd = await db.get_withdrawal_request(wd_id)
    if not wd:
        await message.answer("⚠️ Заявка не найдена.")
        await state.clear()
        return

    await db.update_withdrawal_status(wd_id, "rejected", reason)
    await state.clear()

    try:
        await bot.send_message(
            chat_id=wd["user_id"],
            text=(
                f"❌ <b>Заявка на вывод средств #{wd_id} была отклонена.</b>\n\n"
                f"⭐️ <b>{wd['amount_stars']} ⭐️</b> возвращены на ваш баланс.\n"
                f"💬 <b>Причина:</b> <i>{reason}</i>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Could not notify user {wd['user_id']}: {e}")

    await message.answer(
        f"❌ <b>Заявка #{wd_id} отклонена.</b>\n{wd['amount_stars']} ⭐️ возвращены партнеру.",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )


# =========================================================================
# 📢 Broadcast (Рассылка всем пользователям)
# =========================================================================

@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return

    db = get_db()
    user_ids = await db.get_all_user_ids()

    await state.set_state(AdminBroadcastState.waiting_for_message)
    await callback.message.edit_text(
        "📢 <b>Рассылка сообщений</b>\n\n"
        f"👥 Всего пользователей в базе: <b>{len(user_ids)} чел.</b>\n\n"
        "Отправьте сообщение, которое хотите разослать (текст, фото с описанием, видео, анимацию или кружочек).\n\n"
        "<i>Перед отправкой вам будет показан предпросмотр сообщения для подтверждения.</i>",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminBroadcastState.waiting_for_message)
async def process_admin_broadcast_message(message: Message, state: FSMContext):
    if not is_admin_filter(message):
        return

    db = get_db()
    user_ids = await db.get_all_user_ids()

    await state.update_data(
        broadcast_from_chat_id=message.chat.id,
        broadcast_message_id=message.message_id
    )
    await state.set_state(AdminBroadcastState.waiting_for_confirm)

    await message.answer("👁 <b>Предпросмотр сообщения для рассылки:</b>", parse_mode="HTML")
    await message.copy_to(chat_id=message.chat.id)

    await message.answer(
        f"📢 <b>Подтверждение рассылки</b>\n\n"
        f"👥 Получателей в базе: <b>{len(user_ids)} чел.</b>\n\n"
        "Нажмите <b>«🚀 Отправить всем»</b> для запуска или отмените действие:",
        reply_markup=get_admin_broadcast_confirm_keyboard(len(user_ids)),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin:broadcast_cancel")
async def cb_admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return

    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Рассылка отменена.</b>",
        reply_markup=get_admin_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast_confirm")
async def cb_admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin_filter(callback):
        return

    data = await state.get_data()
    from_chat_id = data.get("broadcast_from_chat_id")
    message_id = data.get("broadcast_message_id")

    await state.clear()

    if not from_chat_id or not message_id:
        await callback.answer("⚠️ Сообщение для рассылки не найдено. Попробуйте снова.", show_alert=True)
        await show_admin_panel(callback.message)
        return

    db = get_db()
    user_ids = await db.get_all_user_ids()

    if not user_ids:
        await callback.message.edit_text(
            "⚠️ <b>В базе нет пользователей для рассылки.</b>",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    status_msg = await callback.message.edit_text(
        f"⏳ <b>Рассылка запущена...</b>\n\n"
        f"Отправка сообщений <b>{len(user_ids)}</b> пользователям.\n"
        f"Пожалуйста, не закрывайте бота до получения отчета.",
        parse_mode="HTML"
    )
    await callback.answer()

    success_count = 0
    blocked_count = 0
    error_count = 0
    start_time = time.time()

    for idx, uid in enumerate(user_ids, 1):
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            success_count += 1
            await db.unmark_user_blocked(uid)
        except TelegramForbiddenError:
            blocked_count += 1
            await db.mark_user_blocked(uid)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(
                    chat_id=uid,
                    from_chat_id=from_chat_id,
                    message_id=message_id
                )
                success_count += 1
                await db.unmark_user_blocked(uid)
            except TelegramForbiddenError:
                blocked_count += 1
                await db.mark_user_blocked(uid)
            except Exception:
                error_count += 1
        except TelegramAPIError as e:
            error_count += 1
            logger.debug(f"Telegram API error broadcasting to {uid}: {e}")
        except Exception as e:
            error_count += 1
            logger.debug(f"Unexpected error broadcasting to {uid}: {e}")

        # Safe rate limit: ~25 msgs/sec
        await asyncio.sleep(0.04)

    elapsed_time = round(time.time() - start_time, 1)

    try:
        await status_msg.edit_text(
            f"📊 <b>Рассылка успешно завершена!</b>\n\n"
            f"👥 Всего получателей: <code>{len(user_ids)}</code>\n"
            f"✅ Успешно доставлено: <code>{success_count}</code>\n"
            f"🚫 Заблокировали бота: <code>{blocked_count}</code>\n"
            f"⚠️ Ошибок отправки: <code>{error_count}</code>\n"
            f"⏱ Затрачено времени: <code>{elapsed_time} сек.</code>",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Could not update broadcast finish message: {e}")
        await callback.message.answer(
            f"📊 <b>Рассылка успешно завершена!</b>\n\n"
            f"👥 Всего получателей: <code>{len(user_ids)}</code>\n"
            f"✅ Успешно доставлено: <code>{success_count}</code>\n"
            f"🚫 Заблокировали бота: <code>{blocked_count}</code>\n"
            f"⚠️ Ошибок отправки: <code>{error_count}</code>\n"
            f"⏱ Затрачено времени: <code>{elapsed_time} сек.</code>",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="HTML"
        )


# =========================================================================
# 👥 Users List (Список всех пользователей)
# =========================================================================

@router.callback_query(F.data.startswith("admin:users_list"))
async def cb_admin_users_list(callback: CallbackQuery, state: FSMContext):
    if not is_admin_filter(callback):
        return
    await state.clear()

    page = 1
    parts = callback.data.split(":")
    if len(parts) >= 3 and parts[2].isdigit():
        page = int(parts[2])

    per_page = 10
    db = get_db()
    data = await db.get_users_list(page=page, per_page=per_page)
    users = data["users"]
    total_count = data["total_count"]
    total_pages = data["total_pages"]
    current_page = data["page"]

    if not users:
        text = "👥 <b>Список пользователей пуст.</b>"
    else:
        start_num = (current_page - 1) * per_page + 1
        lines = [
            f"👥 <b>Пользователи бота</b> (Стр. <b>{current_page}/{total_pages}</b> · Всего: <b>{total_count}</b>)\n"
        ]

        for i, u in enumerate(users, start_num):
            username = (u.get("username") or "").strip()
            first_name = (u.get("first_name") or "").strip()
            if first_name in ("...", "-", "_", "—", ".", "null", "None"):
                first_name = ""
            uid = u["user_id"]

            # Concise name / username format
            if username and first_name and first_name.lower() != username.lower():
                user_title = f"{first_name} (@{username})"
            elif username:
                user_title = f"@{username}"
            elif first_name:
                user_title = f"{first_name}"
            else:
                user_title = ""

            # Minimalist badges (only if active)
            badges = []
            if u.get("is_vip_user"):
                badges.append("👑")
            if u.get("is_partner"):
                promo = f" <i>[{u['invited_by_promo']}]</i>" if u.get("invited_by_promo") else ""
                badges.append(f"🤝{promo}")
            if u.get("is_blocked"):
                badges.append("🚫")

            refs_cnt = u.get("referrals_count", 0)
            if refs_cnt > 0:
                badges.append(f"👥{refs_cnt}")

            balance = u.get("partner_balance", 0)
            if balance > 0:
                badges.append(f"💰{balance}⭐️")

            badge_str = f" {' '.join(badges)}" if badges else ""

            if user_title:
                lines.append(f"<b>{i}.</b> {user_title} · <code>{uid}</code>{badge_str}")
            else:
                lines.append(f"<b>{i}.</b> <code>{uid}</code>{badge_str}")

        text = "\n".join(lines)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_users_keyboard(page=current_page, total_pages=total_pages),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=get_admin_users_keyboard(page=current_page, total_pages=total_pages),
            parse_mode="HTML"
        )
    await callback.answer()


# =========================================================================
# 🚫 Blocked Users (Пользователи, заблокировавшие бота)
# =========================================================================

@router.callback_query(F.data.startswith("admin:blocked_users"))
async def cb_admin_blocked_users(callback: CallbackQuery):
    if not is_admin_filter(callback):
        return

    page = 1
    parts = callback.data.split(":")
    if len(parts) >= 3 and parts[2].isdigit():
        page = int(parts[2])

    per_page = 10
    db = get_db()
    data = await db.get_blocked_users_paged(page=page, per_page=per_page)
    blocked_users = data["users"]
    total_blocked = data["total_count"]
    total_pages = data["total_pages"]
    current_page = data["page"]

    all_users = await db.get_all_user_ids()
    total_users = len(all_users)

    if not blocked_users and total_blocked == 0:
        text = (
            "🚫 <b>Пользователи, заблокировавшие бота</b>\n\n"
            f"👥 Всего пользователей в базе: <b>{total_users}</b>\n"
            "🟢 <b>Заблокировавших бота: 0</b>\n\n"
            "<i>Список блокировок обновляется автоматически во время каждой рассылки.</i>"
        )
    else:
        start_num = (current_page - 1) * per_page + 1
        page_info = f" (Стр. <b>{current_page}/{total_pages}</b>)" if total_pages > 1 else ""
        lines = [
            f"🚫 <b>Пользователи, заблокировавшие бота</b>{page_info}\n",
            f"👥 Всего пользователей в базе: <b>{total_users}</b>",
            f"🔴 Заблокировали бота: <b>{total_blocked}</b>\n",
            "<i>(Статус фиксируется при попытке отправки сообщения во время рассылки)</i>\n",
            "<b>Список заблокировавших:</b>"
        ]

        for idx, u in enumerate(blocked_users, start_num):
            name = f"@{u['username']}" if u.get("username") else (u.get("first_name") or f"ID {u['user_id']}")
            blocked_date = str(u.get("blocked_at") or "Недавно")[:16]
            lines.append(f"{idx}. {name} (<code>{u['user_id']}</code>) — <i>{blocked_date}</i>")

        text = "\n".join(lines)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_blocked_users_keyboard(page=current_page, total_pages=total_pages),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=get_admin_blocked_users_keyboard(page=current_page, total_pages=total_pages),
            parse_mode="HTML"
        )
    await callback.answer()


