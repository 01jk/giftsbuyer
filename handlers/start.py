import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
from database import get_db
from keyboards.common_kb import get_start_keyboard, get_back_to_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    db = get_db()
    await db.register_user(user_id, username, first_name)
    
    payload = command.args.strip() if command and command.args else ""
    is_promo_activated = False
    promo_data = None

    # 1. Custom Promo Links
    if payload and not payload.startswith("ref_"):
        promo = await db.get_promo_link(payload)
        if not promo and payload.lower() in ("forum", "promo_forum", "promo"):
            promo = await db.get_promo_link("forum")

        if promo and promo.get("is_active", 1):
            await db.activate_partner(
                user_id=user_id,
                days=promo.get("duration_days", 30),
                gift_markup=promo.get("gift_markup_percent", 15.0),
                stars_markup=promo.get("stars_markup_percent", 10.0)
            )
            await db.increment_promo_activations(promo["code"])
            await db.set_user_promo_source(user_id, promo["code"])
            is_promo_activated = True
            promo_data = promo
    
    # 2. Referral Link (ref_123456)
    if not is_promo_activated and payload.startswith("ref_"):
        ref_arg = payload[4:]
        if ref_arg.isdigit():
            referrer_id = int(ref_arg)
            bound = await db.add_referral_if_none(user_id, referrer_id)
            if bound:
                try:
                    ref_user_label = f"@{username}" if username else f"{first_name or 'Пользователь'} (ID: <code>{user_id}</code>)"
                    await message.bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"🎉 <b>У вас новый реферал!</b>\n\n"
                            f"Пользователь {ref_user_label} присоединился по вашей партнерской ссылке.\n"
                            "Теперь вы будете получать <b>20% маржи</b> со всех его покупок подарков и звезд!"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify referrer {referrer_id}: {e}")

    is_vip = await db.is_vip(user_id)
    is_partner = await db.is_active_partner(user_id)
    is_admin = user_id in ADMIN_IDS

    if is_vip:
        vip_badge = "\n👑 <b>Ваш статус: VIP (покупка без комиссии)</b>"
    elif is_partner:
        gift_m = await db.get_user_gift_markup(user_id)
        stars_m = await db.get_user_stars_markup(user_id)
        vip_badge = f"\n🤝 <b>Партнерский статус активен:</b> наценка {gift_m}% на подарки, {stars_m}% на звезды"
    else:
        vip_badge = ""

    if is_promo_activated and promo_data:
        p_name = promo_data.get("name") or "Специальная акция"
        p_days = promo_data.get("duration_days", 30)
        p_gift = float(promo_data.get("gift_markup_percent", 15.0))
        p_stars = float(promo_data.get("stars_markup_percent", 10.0))
        p_gift_str = f"{int(p_gift)}" if p_gift.is_integer() else f"{p_gift}"
        p_stars_str = f"{int(p_stars)}" if p_stars.is_integer() else f"{p_stars}"

        promo_banner = (
            f"🎉 <b>Промо-ссылка «{p_name}» успешно активирована!</b>\n\n"
            f"Вам на <b>{p_days} дней</b> предоставлены специальные условия:\n"
            f"🎁 <b>Наценка на подарки:</b> <code>{p_gift_str}%</code>\n"
            f"⭐️ <b>Наценка на звёзды:</b> <code>{p_stars_str}%</code>\n"
            f"🤝 <b>Доступ к партнерской программе:</b> вы можете получать <b>20% маржи</b> с покупок ваших друзей!\n\n"
            "➖➖➖➖➖➖➖➖➖➖\n\n"
        )
    else:
        promo_banner = ""

    text = (
        f"{promo_banner}"
        f"✨ <b>Добро пожаловать в Telegram Gifts Buyer Bot!</b>\n\n"
        f"Здесь вы можете приобрести любые скрытые и эксклюзивные подарки Telegram по их ID.{vip_badge}\n\n"
        f"🔹 <b>Отправка подарка:</b>\n"
        f"• <b>От бота:</b> без авторизации (оплата полной стоимости звёздами боту).\n"
        f"🛡️ <i>Все платежи защищены автоматическим возвратом звёзд (refund) в случае сбоев.</i>\n\n"
        f"Нажмите кнопку ниже или <b>просто отправьте ID подарка</b> в чат:\n\n"
        f"<i>powered by @GiftChanges (api.changes.tg)</i>"
    )

    await message.answer(text, reply_markup=get_start_keyboard(is_admin=is_admin), parse_mode="HTML")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    db = get_db()
    is_vip = await db.is_vip(user_id)
    is_admin = user_id in ADMIN_IDS
    vip_badge = "\n👑 <b>Ваш статус: VIP (покупка без комиссии)</b>" if is_vip else ""

    text = (
        f"✨ <b>Главное меню</b>\n\n"
        f"Отправьте <b>ID подарка</b> числом в чат или нажмите кнопку:{vip_badge}"
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_start_keyboard(is_admin=is_admin),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=get_start_keyboard(is_admin=is_admin),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "help_info")
async def cb_help_info(callback: CallbackQuery):
    text = (
        "ℹ️ <b>Как работает покупка подарков по ID?</b>\n\n"
        "1️⃣ <b>Ввод ID подарка:</b>\n"
        "Отправьте уникальный числовой ID подарка (например, <code>5801108895304779062</code>).\n\n"
        "2️⃣ <b>Проверка доступности:</b>\n"
        "Бот проверяет через Telegram API, доступен ли подарок к покупке, отображает его стикер и точную официальную стоимость.\n\n"
        "3️⃣ <b>Отправка:</b>\n"
        "• <b>От бота:</b> Бот сам отправляет подарок получателю. Вы оплачиваете стоимость подарка + комиссию сервиса в звёздах.\n"
        "4️⃣ <b>Гарантия возврата:</b>\n"
        "Если подарок окажется недоступен или произойдет сбой, Telegram Stars автоматически возвращаются на ваш баланс!"
    )
    await callback.message.edit_text(text, reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")
    await callback.answer()
