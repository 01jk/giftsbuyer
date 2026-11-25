import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from database import get_db
from config import ADMIN_IDS
from states.gift_states import PartnerWithdrawState, PartnerApplicationState
from keyboards.partner_kb import (
    get_partner_cabinet_keyboard,
    get_withdrawal_memo_kb,
    get_partner_back_kb
)
from keyboards.admin_kb import get_admin_app_card_keyboard, get_admin_withdrawal_card_keyboard
from keyboards.common_kb import get_back_to_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("partner"))
@router.callback_query(F.data == "partner:open")
async def show_partner_cabinet(event: Message | CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id
    db = get_db()
    stats = await db.get_partner_stats(user_id)
    bot_user = await bot.get_me()
    bot_username = bot_user.username or ""

    is_partner = stats["is_partner"]
    is_expired = stats["is_expired"]
    balance = stats["partner_balance"]
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    if is_partner and not is_expired:
        hold_line = f"\n⏳ <b>Холд вывода (21 день):</b> {stats['hold_left_str']}" if stats["hold_active"] else ""
        
        text = (
            "🤝 <b>Личный кабинет партнера</b>\n\n"
            f"💼 <b>Баланс к выводу:</b> <b>{balance} ⭐️</b>{hold_line}\n"
            f"⏳ <b>Срок действия программы:</b> <code>{stats['time_left_str']}</code>\n"
            f"🎁 <b>Ваша наценка на подарки:</b> <code>{stats['gift_markup_percent']}%</code>\n"
            f"⭐️ <b>Ваша наценка на звезды:</b> <code>{stats['stars_markup_percent']}%</code>\n\n"
            "📊 <b>Ваша реферальная статистика:</b>\n"
            f"• Всего приглашено: <b>{stats['total_referrals']}</b> чел.\n"
            f"• Активных рефералов (5+ покупок): <b>{stats['active_referrals_5plus']}</b> чел.\n"
            f"• Всего заработано: <b>{stats['total_earned_stars']} ⭐️</b> (20% маржи от всех покупок)\n\n"
            "🔗 <b>Ваша персональная реферальная ссылка:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            "<i>💡 Отправляйте ссылку друзьям или клиентам. При покупке подарков или звезд вы будете получать 20% маржи на баланс!</i>"
        )
    elif is_expired:
        text = (
            "⌛️ <b>Срок вашей партнерской программы истек</b>\n\n"
            f"💼 <b>Текущий баланс:</b> <b>{balance} ⭐️</b>\n"
            f"👥 Всего рефералов: <b>{stats['total_referrals']}</b> (Активных 5+: <b>{stats['active_referrals_5plus']}</b>)\n"
            f"💰 Заработано за все время: <b>{stats['total_earned_stars']} ⭐️</b>\n\n"
            "Вы можете подать заявку на продление партнерской программы. Администрация рассмотрит вашу заявку на основе статистики приглашенных рефералов."
        )
    else:
        text = (
            "🤝 <b>Партнерская программа</b>\n\n"
            "Станьте нашим официальным партнером и зарабатывайте на покупках приглашенных пользователей!\n\n"
            "🔹 <b>Преимущества для партнеров:</b>\n"
            "• 💰 <b>20% маржи</b> со всех покупок подарков и Telegram Stars вашими рефералами.\n"
            "• 💎 <b>Вывод средств в TON</b> (доступен от 1000 ⭐️).\n\n"
            "Нажмите кнопку ниже, чтобы подать заявку на участие в программе:"
        )

    reply_markup = get_partner_cabinet_keyboard(is_active=(is_partner and not is_expired), is_expired=is_expired, balance=balance)

    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@router.callback_query(F.data == "partner:referrals_list")
async def cb_partner_referrals_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    db = get_db()
    stats = await db.get_partner_stats(user_id)
    referrals = stats.get("referrals", [])

    if not referrals:
        text = "📋 <b>У вас пока нет приглашенных рефералов.</b>\n\nПоделитесь вашей реферальной ссылкой, чтобы начать зарабатывать!"
    else:
        lines = []
        for i, ref in enumerate(referrals[:30], 1):
            name = f"@{ref['username']}" if ref.get("username") else f"ID: {ref['user_id']}"
            orders_count = ref.get("total_orders", 0)
            badge = " 🔥" if orders_count >= 5 else ""
            lines.append(f"{i}. {name} — <b>{orders_count}</b> заказов{badge}")
        
        text = (
            f"📋 <b>Список ваших рефералов ({len(referrals)} чел.):</b>\n\n"
            + "\n".join(lines)
            + ("\n\n<i>🔥 — рефералы с 5+ покупками</i>" if any(r.get("total_orders", 0) >= 5 for r in referrals) else "")
        )

    await callback.message.edit_text(text, reply_markup=get_partner_back_kb(), parse_mode="HTML")
    await callback.answer()


# Application for regular user
@router.callback_query(F.data == "partner:apply_new")
async def cb_apply_new_partner(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PartnerApplicationState.waiting_for_note)
    text = (
        "📝 <b>Заявка на партнерскую программу</b>\n\n"
        "Расскажите кратко, откуда вы планируете привлекать пользователей (канал, чат, форум, друзья) "
        "или просто напишите «Хочу стать партнером»:"
    )
    await callback.message.edit_text(text, reply_markup=get_partner_back_kb(), parse_mode="HTML")
    await callback.answer()

@router.message(PartnerApplicationState.waiting_for_note, F.text)
async def process_partner_application_note(message: Message, state: FSMContext, bot: Bot):
    note = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    db = get_db()
    app_id = await db.create_partner_application(user_id=user_id, app_type="new", note=note)
    await state.clear()

    await message.answer(
        "✅ <b>Ваша заявка успешно отправлена администрации!</b>\n\n"
        "Мы рассмотрим ее в ближайшее время и пришлем вам уведомление с решением.",
        reply_markup=get_back_to_menu_keyboard(),
        parse_mode="HTML"
    )

    # Notify admins
    user_label = f"@{username}" if username else f"{first_name} (ID: <code>{user_id}</code>)"
    admin_text = (
        "📬 <b>Новая заявка на партнерскую программу!</b>\n\n"
        f"👤 <b>Пользователь:</b> {user_label}\n"
        f"📝 <b>Комментарий:</b> {note}\n"
        f"🆔 Номер заявки: <code>#{app_id}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                reply_markup=get_admin_app_card_keyboard(app_id),
                parse_mode="HTML"
            )
        except Exception:
            pass


# Renewal application for expired partner
@router.callback_query(F.data == "partner:request_renewal")
async def cb_request_renewal(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    db = get_db()

    stats = await db.get_partner_stats(user_id)
    app_id = await db.create_partner_application(
        user_id=user_id,
        app_type="renewal",
        note=f"Продление программы. Рефералов: {stats['total_referrals']}, 5+ заказов: {stats['active_referrals_5plus']}, Заработано: {stats['total_earned_stars']} ⭐️"
    )

    await callback.message.edit_text(
        "✅ <b>Заявка на продление успешно отправлена!</b>\n\n"
        "Администрация рассмотрит вашу статистику и пришлет решение.",
        reply_markup=get_partner_back_kb(),
        parse_mode="HTML"
    )
    await callback.answer("Заявка отправлена!")

    # Notify admins
    user_label = f"@{username}" if username else f"{first_name} (ID: <code>{user_id}</code>)"
    admin_text = (
        "📬 <b>Заявка на ПРОДЛЕНИЕ партнерской программы!</b>\n\n"
        f"👤 <b>Партнер:</b> {user_label}\n"
        "📊 <b>Статистика работы:</b>\n"
        f"• Всего рефералов: <b>{stats['total_referrals']}</b> чел.\n"
        f"• Активных (5+ покупок): <b>{stats['active_referrals_5plus']}</b> чел.\n"
        f"• Всего заработано: <b>{stats['total_earned_stars']} ⭐️</b>\n"
        f"• Текущий баланс: <b>{stats['partner_balance']} ⭐️</b>\n\n"
        f"🆔 Номер заявки: <code>#{app_id}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                reply_markup=get_admin_app_card_keyboard(app_id),
                parse_mode="HTML"
            )
        except Exception:
            pass


# Partner Withdrawal Flow
@router.callback_query(F.data == "partner:withdraw")
async def cb_partner_withdraw(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db = get_db()
    stats = await db.get_partner_stats(user_id)
    balance = stats["partner_balance"]

    if balance < 1000:
        await callback.answer(
            f"⚠️ Минимальная сумма для вывода — 1000 ⭐️.\nВаш текущий баланс: {balance} ⭐️",
            show_alert=True
        )
        return

    if stats["hold_active"]:
        await callback.answer(
            f"⏳ Вывод средств временно недоступен.\nХолд действует еще: {stats['hold_left_str']}",
            show_alert=True
        )
        return

    await state.set_state(PartnerWithdrawState.waiting_for_address)
    await state.update_data(withdraw_amount=balance)

    text = (
        f"💸 <b>Заявка на вывод средств</b>\n\n"
        f"⭐️ Сумма к выводу: <b>{balance} ⭐️</b>\n\n"
        "Введите ваш <b>TON кошелек</b> (адрес) для получения выплаты:"
    )
    await callback.message.edit_text(text, reply_markup=get_partner_back_kb(), parse_mode="HTML")
    await callback.answer()

@router.message(PartnerWithdrawState.waiting_for_address, F.text)
async def process_withdraw_address(message: Message, state: FSMContext):
    address = message.text.strip()
    if len(address) < 20:
        await message.answer("⚠️ Некорректный адрес кошелька. Пожалуйста, введите правильный TON адрес:")
        return

    await state.update_data(ton_address=address)
    await state.set_state(PartnerWithdrawState.waiting_for_memo)

    text = (
        f"💎 TON адрес: <code>{address}</code>\n\n"
        "Если вашей бирже/кошельку требуется <b>Memo / Comment / Tag</b>, введите его ниже.\n"
        "Если Memo не требуется, нажмите «⏩ Пропустить Memo»:"
    )
    await message.answer(text, reply_markup=get_withdrawal_memo_kb(), parse_mode="HTML")

@router.callback_query(PartnerWithdrawState.waiting_for_memo, F.data == "partner:skip_memo")
async def cb_skip_memo(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await finish_withdrawal(callback.message, state, bot, memo=None, user_id=callback.from_user.id)
    await callback.answer()

@router.message(PartnerWithdrawState.waiting_for_memo, F.text)
async def process_withdraw_memo(message: Message, state: FSMContext, bot: Bot):
    memo = message.text.strip()
    await finish_withdrawal(message, state, bot, memo=memo, user_id=message.from_user.id)

async def finish_withdrawal(message: Message, state: FSMContext, bot: Bot, memo: str | None, user_id: int):
    data = await state.get_data()
    amount = data.get("withdraw_amount", 0)
    ton_address = data.get("ton_address", "")
    await state.clear()

    db = get_db()
    # Check current balance again
    user_info = await db.get_user(user_id)
    current_balance = user_info.get("partner_balance", 0) if user_info else 0
    if current_balance < amount or amount <= 0:
        await message.answer("⚠️ Недостаточно средств на балансе для совершения вывода.", reply_markup=get_back_to_menu_keyboard())
        return

    req_id = await db.create_withdrawal_request(
        user_id=user_id,
        amount_stars=amount,
        ton_address=ton_address,
        memo=memo
    )

    memo_line = f"\n📝 Memo: <code>{memo}</code>" if memo else ""
    await message.answer(
        "✅ <b>Заявка на вывод средств успешно создана!</b>\n\n"
        f"⭐️ Сумма: <b>{amount} ⭐️</b>\n"
        f"💎 TON адрес: <code>{ton_address}</code>{memo_line}\n\n"
        "Администратор обработает вашу выплату в ближайшее время.",
        reply_markup=get_back_to_menu_keyboard(),
        parse_mode="HTML"
    )

    # Notify admins
    username = message.from_user.username
    first_name = message.from_user.first_name
    user_label = f"@{username}" if username else f"{first_name} (ID: <code>{user_id}</code>)"
    admin_text = (
        "💸 <b>Новая заявка на вывод средств партнера!</b>\n\n"
        f"👤 <b>Партнер:</b> {user_label}\n"
        f"⭐️ <b>Сумма:</b> <b>{amount} ⭐️</b>\n"
        f"💎 <b>TON Адрес:</b> <code>{ton_address}</code>{memo_line}\n"
        f"🆔 Заявка: <code>#{req_id}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                reply_markup=get_admin_withdrawal_card_keyboard(req_id),
                parse_mode="HTML"
            )
        except Exception:
            pass
