import uuid
import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.fsm.context import FSMContext
from database import get_db
from states.gift_states import GiftOrderState
from services.pricing_service import calculate_gift_price
from services.payment_service import PaymentService
from services.telethon_service import TelethonService
from services.catalog_service import catalog_service
from keyboards.common_kb import get_cancel_keyboard, get_back_to_menu_keyboard
from keyboards.catalog_kb import NUM_EMOJIS
from keyboards.gift_kb import (
    get_recipient_keyboard,
    get_signature_keyboard,
    get_channel_selection_keyboard,
    get_add_channel_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "cancel_order")
async def cb_cancel_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "❌ <b>Заказ отменен.</b>",
        reply_markup=get_back_to_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer("Заказ отменен")


# Step 1: Start Buy Flow -> Multi-gift Checkout
@router.callback_query(F.data == "catalog:checkout")
async def cb_catalog_checkout(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    gifts = data.get("selected_gifts", [])
    if not gifts:
        await callback.answer("⚠️ Выберите хотя бы один подарок в каталоге!", show_alert=True)
        return

    user_id = callback.from_user.id
    base_stars = sum(g.get("base_stars", g.get("stars", 50)) for g in gifts)
    total_stars, fee_stars, is_vip = await calculate_gift_price(user_id, base_stars)

    await state.update_data(
        gifts=gifts,
        gift_id=gifts[0]["gift_id"],
        base_stars=base_stars,
        total_stars=total_stars,
        fee_stars=fee_stars,
        is_vip=is_vip
    )

    count_text = f" ({len(gifts)} шт.)" if len(gifts) > 1 else ""
    text = (
        f"👤 <b>Кому вы хотите отправить подарки{count_text}?</b>\n\n"
        "• <b>Для себя</b> — подарки будут отправлены в ваш профиль.\n"
        "• <b>Для друга</b> — потребуется указать @username или Telegram ID получателя.\n"
        "• <b>Для канала</b> — отправка в ваш закрытый или открытый канал."
    )

    try:
        await callback.message.edit_text(text, reply_markup=get_recipient_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_recipient_keyboard(), parse_mode="HTML")
    await callback.answer()


# Single Gift Purchase
@router.callback_query(F.data.startswith("buy_gift:"))
async def cb_buy_gift(callback: CallbackQuery, state: FSMContext):
    gift_id = int(callback.data.split(":", 1)[1])
    db = get_db()
    
    gift_info = await db.get_catalog_gift_by_id(gift_id)
    if gift_info:
        title = gift_info.get("title") or catalog_service.get_gift_title(gift_id)
        stars = gift_info.get("stars", 50)
    else:
        title = catalog_service.get_gift_title(gift_id)
        stars = 50

    gifts = [{"gift_id": gift_id, "title": title, "stars": stars}]
    base_stars = stars
    total_stars, fee_stars, is_vip = await calculate_gift_price(callback.from_user.id, base_stars)

    await state.update_data(
        gifts=gifts,
        gift_id=gift_id,
        base_stars=base_stars,
        total_stars=total_stars,
        fee_stars=fee_stars,
        is_vip=is_vip
    )

    text = (
        "👤 <b>Кому вы хотите отправить подарок?</b>\n\n"
        "• <b>Для себя</b> — подарок будет отправлен в ваш профиль.\n"
        "• <b>Для друга</b> — потребуется указать @username или Telegram ID получателя.\n"
        "• <b>Для канала</b> — отправка в ваш закрытый или открытый канал."
    )

    try:
        await callback.message.edit_text(text, reply_markup=get_recipient_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_recipient_keyboard(), parse_mode="HTML")
    await callback.answer()

# Recipient: Self
@router.callback_query(F.data == "recipient:self")
async def cb_recipient_self(callback: CallbackQuery, state: FSMContext):
    user_peer = str(callback.from_user.id)
    await state.update_data(target_peer=user_peer, recipient_type="self")
    await ask_signature(callback.message, state)
    await callback.answer()

# Recipient: Friend
@router.callback_query(F.data == "recipient:friend")
async def cb_recipient_friend(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GiftOrderState.waiting_for_recipient)
    text = (
        "👥 <b>Укажите получателя подарка</b>\n\n"
        "Отправьте @юзернейм (например: <code>@durov</code>) или числовой Telegram ID друга:"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(GiftOrderState.waiting_for_recipient, F.text)
async def process_friend_recipient(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    if not text.lstrip("-").isdigit() and not text.startswith("@"):
        text = f"@{text}"
    
    await state.update_data(target_peer=text, recipient_type="friend")
    await state.set_state(None)
    await ask_signature(message, state)

# Recipient: Channel
@router.callback_query(F.data == "recipient:channel")
async def cb_recipient_channel(callback: CallbackQuery, state: FSMContext, bot: Bot):
    db = get_db()
    user_id = callback.from_user.id
    channels = await db.get_user_channels(user_id)
    
    bot_user = await bot.get_me()
    bot_username = bot_user.username or ""

    if channels:
        text = (
            "📢 <b>Выберите канал для отправки подарков:</b>\n\n"
            "Ниже показаны ваши привязанные закрытые каналы, в которых бот назначен администратором.\n"
            "Также вы можете привязать новый канал или отправить подарок в открытый канал по @username."
        )
    else:
        text = (
            "📢 <b>Отправка подарков на канал</b>\n\n"
            "• <b>Закрытый канал:</b> Добавьте бота в канал и назначьте его администратором — канал автоматически привяжется и появится в списке ниже.\n"
            "• <b>Открытый канал:</b> Нажмите «Ввести @username» и укажите публичный юзернейм канала."
        )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_channel_selection_keyboard(channels, bot_username),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=get_channel_selection_keyboard(channels, bot_username),
            parse_mode="HTML"
        )
    await callback.answer("Список каналов обновлен")

@router.callback_query(F.data.startswith("channel_select:"))
async def cb_channel_select(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":", 1)[1])
    db = get_db()
    user_id = callback.from_user.id
    ch_info = await db.get_user_channel_by_id(user_id, channel_id)
    
    title = ch_info.get("channel_title", f"Канал {channel_id}") if ch_info else f"Канал {channel_id}"
    
    await state.update_data(
        target_peer=str(channel_id),
        target_name=title,
        recipient_type="channel",
        send_method="bot", # Channel gifts are sent via bot
        is_anonymous=False
    )

    text = "✍️ <b>Желаете ли вы добавить сообщение/подпись к подаркам?</b>"
    await callback.message.edit_text(text, reply_markup=get_signature_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "channel_bind_info")
async def cb_channel_bind_info(callback: CallbackQuery, bot: Bot):
    bot_user = await bot.get_me()
    bot_username = bot_user.username or ""
    
    text = (
        "ℹ️ <b>Как привязать закрытый канал к боту:</b>\n\n"
        f"1. Нажмите кнопку <b>«➕ Добавить бота в канал»</b> ниже (или добавьте вручную <code>@{bot_username}</code> в список администраторов вашего канала).\n"
        "2. Назначьте бота <b>Администратором</b> (достаточно любых базовых прав).\n"
        "3. Бот мгновенно определит ваш канал, привяжет его к вашему профилю и пришлёт подтверждение в этот чат.\n"
        "4. После этого нажмите <b>«🔄 Проверить привязку»</b>, и канал будет готов к получению подарков!"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_add_channel_keyboard(bot_username),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "channel_manual")
async def cb_channel_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GiftOrderState.waiting_for_channel_manual)
    text = (
        "✍️ <b>Введите @username открытого канала:</b>\n\n"
        "Например: <code>@durov</code> или <code>@my_channel</code>"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(GiftOrderState.waiting_for_channel_manual, F.text)
async def process_channel_manual_input(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.lstrip("-").isdigit() and not text.startswith("@"):
        text = f"@{text}"
    
    await state.update_data(
        target_peer=text,
        target_name=text,
        recipient_type="channel",
        send_method="bot",
        is_anonymous=False
    )
    await state.set_state(None)

    prompt = "✍️ <b>Желаете ли вы добавить сообщение/подпись к подаркам?</b>"
    await message.answer(prompt, reply_markup=get_signature_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "channel_back_to_recipient")
async def cb_channel_back_to_recipient(callback: CallbackQuery, state: FSMContext):
    text = (
        "👤 <b>Кому вы хотите отправить подарок?</b>\n\n"
        "• <b>Для себя</b> — подарок будет отправлен в ваш профиль.\n"
        "• <b>Для друга</b> — потребуется указать @username или Telegram ID получателя.\n"
        "• <b>Для канала</b> — отправка в ваш закрытый или открытый канал."
    )
    await callback.message.edit_text(text, reply_markup=get_recipient_keyboard(), parse_mode="HTML")
    await callback.answer()

# Step 2: Choose Sender Method
async def ask_signature(message: Message, state: FSMContext):
    await state.update_data(send_method="bot", is_anonymous=False)
    text = "Добавить сообщение к подарку?"
    try:
        await message.edit_text(text, reply_markup=get_signature_keyboard())
    except Exception:
        await message.answer(text, reply_markup=get_signature_keyboard())

@router.callback_query(F.data == "signature:add")
async def cb_signature_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GiftOrderState.waiting_for_signature)
    text = (
        "✍️ <b>Введите текст сообщения для подарков:</b>\n"
        "<i>(Максимум 128 символов)</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(GiftOrderState.waiting_for_signature, F.text)
async def process_signature_text(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()[:128]
    await state.update_data(gift_message=text)
    await show_order_summary_and_invoice(message, state, bot)

@router.callback_query(F.data == "signature:none")
async def cb_signature_none(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(gift_message=None)
    await show_order_summary_and_invoice(callback.message, state, bot)
    await callback.answer()

# Step 5: Summary and Invoice Generation
async def show_order_summary_and_invoice(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = message.chat.id
    db = get_db()

    gifts = data.get("gifts")
    if not gifts:
        gift_id = data.get("gift_id", 50)
        gifts = [{"gift_id": gift_id, "title": data.get("gift_title", f"Подарок #{gift_id}"), "stars": data.get("base_stars", 50)}]

    primary_gift_id = gifts[0]["gift_id"]
    target_peer = data.get("target_peer")
    send_method = "bot"
    is_anonymous = data.get("is_anonymous", False)
    gift_message = data.get("gift_message")
    
    base_stars = sum(g.get("stars", 50) for g in gifts)
    total_stars, fee_stars, is_vip = await calculate_gift_price(user_id, base_stars)
    
    order_id = str(uuid.uuid4())[:8]

    amount_to_pay = total_stars
    price_desc = f"Подарки ({base_stars} ⭐) + комиссия ({fee_stars} ⭐)"

    order_data = {
        "order_id": order_id,
        "user_id": user_id,
        "gift_id": primary_gift_id,
        "gifts_data": gifts,
        "target_peer": target_peer,
        "send_method": send_method,
        "is_anonymous": 1 if is_anonymous else 0,
        "message": gift_message,
        "base_stars": base_stars,
        "total_stars": total_stars,
        "fee_stars": fee_stars,
        "charge_id": None,
        "status": "pending_payment",
        "error_message": None
    }
    await db.create_order(order_data)
    await state.update_data(current_order_id=order_id, amount_to_pay=amount_to_pay, gifts=gifts)

    # Create Telegram Stars Invoice
    prices = [LabeledPrice(label="XTR", amount=amount_to_pay)]
    
    gifts_lines = []
    for i, g in enumerate(gifts):
        num = NUM_EMOJIS.get(i + 1, f"[{i+1}]")
        gifts_lines.append(f"{num} <b>{g.get('title', 'Подарок')}</b> (<code>{g['gift_id']}</code>) — {g.get('stars', 50)} ⭐️")
    gifts_text = "\n".join(gifts_lines)

    summary_text = (
        f"🧾 <b>Подтверждение заказа #{order_id}</b>\n\n"
        f"🎁 <b>Выбранные подарки ({len(gifts)} шт. в порядке отправки):</b>\n"
        f"{gifts_text}\n\n"
        f"🎯 <b>Получатель:</b> <code>{target_peer}</code>\n"
        f"🚀 <b>Метод:</b> От бота\n"
        f"🕶️ <b>Анонимно:</b> {'Да' if is_anonymous else 'Нет'}\n"
        f"✍️ <b>Подпись:</b> {gift_message if gift_message else '<i>Без подписи</i>'}\n\n"
        f"💎 <b>Сумма подарков:</b> {base_stars} ⭐️\n"
        f"🏷️ <b>Комиссия:</b> {fee_stars} ⭐️\n"
        f"💰 <b>К оплате в боте:</b> <b>{amount_to_pay} ⭐️</b>\n"
        f"ℹ️ {price_desc}\n\n"
        f"<i>Нажмите кнопку ниже для оплаты звёздами Telegram Stars.</i>"
    )

    try:
        title = f"Покупка подарков ({len(gifts)} шт.)" if len(gifts) > 1 else f"Покупка подарка #{primary_gift_id}"
        await bot.send_invoice(
            chat_id=message.chat.id,
            title=title,
            description=f"Оплата заказа #{order_id} ({amount_to_pay} Stars)",
            payload=f"order_{order_id}",
            currency="XTR",
            prices=prices,
            provider_token="",
            reply_markup=PaymentService.create_invoice_keyboard(amount_to_pay)
        )
    except Exception as e:
        logger.error(f"Error sending invoice: {e}")
        await message.answer(f"❌ Ошибка формирования счета: {e}")

# Pre-checkout query
@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

# Successful payment
@router.message(F.successful_payment)
async def on_successful_payment(message: Message, state: FSMContext, bot: Bot):
    payload = message.successful_payment.invoice_payload
    charge_id = message.successful_payment.telegram_payment_charge_id
    user_id = message.from_user.id
    
    logger.info(f"Payment received from user {user_id}: payload={payload}, charge_id={charge_id}")
    
    db = get_db()
    if not payload.startswith("order_"):
        return

    order_id = payload.split("order_", 1)[1]
    order = await db.get_order(order_id)
    
    if not order:
        await message.answer("⚠️ Заказ не найден в базе данных.")
        return

    await db.update_order_status(order_id, "paid", charge_id=charge_id)
    await state.update_data(current_order_id=order_id, charge_id=charge_id)

    send_method = order["send_method"]
    target_peer = order["target_peer"]
    is_anon = bool(order["is_anonymous"])
    gift_msg = order["message"]
    gifts = order.get("gifts") or [{"gift_id": order["gift_id"], "title": f"Подарок #{order['gift_id']}", "stars": order.get("base_stars", 50)}]

    if send_method == "bot":
        total_count = len(gifts)
        status_msg = await message.answer(
            f"⏳ <b>Оплата получена! Отправляем подарки ({total_count} шт.) в выбранном порядке...</b>",
            parse_mode="HTML"
        )

        target_user_id = None
        target_chat_id = None
        target_str = str(target_peer).strip()
        try:
            if target_str.lower() == "me" or target_str == str(user_id):
                target_user_id = user_id
            elif target_str.startswith("-100") or (target_str.startswith("-") and target_str[1:].isdigit()):
                target_chat_id = int(target_str)
            elif target_str.isdigit():
                target_user_id = int(target_str)
            else:
                if not target_str.startswith("@"):
                    target_str = f"@{target_str}"
                try:
                    chat_info = await bot.get_chat(target_str)
                    if chat_info.type in ["channel", "supergroup", "group"]:
                        target_chat_id = chat_info.id
                    else:
                        target_user_id = chat_info.id
                except Exception as chat_err:
                    logger.warning(f"get_chat failed for {target_str}: {chat_err}, will attempt direct send_gift")
                    # If target is username, default to trying as chat_id
                    target_chat_id = target_str
        except Exception as e:
            logger.warning(f"Error resolving target {target_str} for bot send: {e}")

        sent_gifts = []
        failed_gifts = []
        last_err = ""

        for idx, g in enumerate(gifts, 1):
            gid = g["gift_id"]
            sent = False
            err_for_gift = ""
            bot_api_err = ""

            # 1. Try Bot API send_gift
            if target_chat_id:
                try:
                    await bot.send_gift(
                        gift_id=str(gid),
                        chat_id=target_chat_id,
                        text=gift_msg,
                        text_parse_mode="HTML" if gift_msg else None
                    )
                    sent = True
                    logger.info(f"Bot API sent gift {gid} ({idx}/{total_count}) to channel {target_chat_id}")
                except Exception as e:
                    bot_api_err = str(e)
                    err_for_gift = bot_api_err
                    logger.warning(f"Bot API send_gift to channel {target_chat_id} failed for {gid} ({bot_api_err}), attempting master session fallback...")
            elif target_user_id:
                try:
                    await bot.send_gift(
                        gift_id=str(gid),
                        user_id=target_user_id,
                        text=gift_msg,
                        text_parse_mode="HTML" if gift_msg else None
                    )
                    sent = True
                    logger.info(f"Bot API sent gift {gid} ({idx}/{total_count}) to user {target_user_id}")
                except Exception as e:
                    bot_api_err = str(e)
                    err_for_gift = bot_api_err
                    logger.warning(f"Bot API send_gift failed for {gid} ({bot_api_err}), attempting master session fallback...")

            # 2. Master session fallback
            if not sent:
                ok, m_msg = await TelethonService.send_gift_from_master_bot(
                    gift_id=gid,
                    target_peer=str(target_peer) if target_peer != "me" else str(user_id),
                    is_anonymous=is_anon,
                    message_text=gift_msg
                )
                if ok:
                    sent = True
                    logger.info(f"Master bot sent gift {gid} ({idx}/{total_count}) to {target_peer}")
                else:
                    # If master session is not configured, preserve the more descriptive Bot API error
                    if "не авторизована" in m_msg and bot_api_err:
                        if "kicked" in bot_api_err.lower():
                            err_for_gift = "Бот был удален или заблокирован в этом канале. Добавьте бота администратором в канал."
                        elif "not found" in bot_api_err.lower():
                            err_for_gift = "Канал не найден или является закрытым. Добавьте бота администратором в канал."
                        else:
                            err_for_gift = f"Ошибка Bot API: {bot_api_err}"
                    else:
                        err_for_gift = m_msg

            if sent:
                sent_gifts.append(g)
            else:
                failed_gifts.append((g, err_for_gift))
                last_err = err_for_gift

            # Delay to ensure strict order in Telegram
            if idx < total_count:
                await asyncio.sleep(1.2)

        try:
            await status_msg.delete()
        except Exception:
            pass

        if len(sent_gifts) == total_count:
            await db.update_order_status(order_id, "completed")
            
            # Process referral reward (20% of fee_stars)
            try:
                order_info = await db.get_order(order_id)
                fee = order_info.get("fee_stars", 0) if order_info else 0
                from services.referral_service import referral_service
                await referral_service.process_referral_reward(
                    order_id=order_id,
                    user_id=order_info.get("user_id", message.chat.id) if order_info else message.chat.id,
                    margin_stars=fee,
                    order_type="gift",
                    bot=message.bot
                )
            except Exception as e:
                logger.warning(f"Error processing referral reward for order {order_id}: {e}")

            gifts_list_text = "\n".join([
                f"{NUM_EMOJIS.get(i+1, f'[{i+1}]')} <b>{g.get('title', 'Подарок')}</b>"
                for i, g in enumerate(sent_gifts)
            ])
            await message.answer(
                f"✅ <b>Все подарки ({total_count} шт.) успешно отправлены!</b> 🎉\n\n"
                f"Получатель <code>{target_peer}</code> получил подарки в строгом порядке:\n"
                f"{gifts_list_text}",
                reply_markup=get_back_to_menu_keyboard(),
                parse_mode="HTML"
            )
            await state.clear()
        elif len(sent_gifts) > 0:
            # Partial success
            await db.update_order_status(order_id, "partial", error_message=last_err)
            sent_text = "\n".join([f"✅ {NUM_EMOJIS.get(i+1, f'[{i+1}]')} <b>{g.get('title', 'Подарок')}</b>" for i, g in enumerate(sent_gifts)])
            failed_text = "\n".join([f"❌ <b>{g.get('title', 'Подарок')}</b> ({err})" for g, err in failed_gifts])
            await message.answer(
                f"⚠️ <b>Заказ выполнен частично ({len(sent_gifts)}/{total_count}):</b>\n\n"
                f"<b>Доставлено:</b>\n{sent_text}\n\n"
                f"<b>Не удалось отправить:</b>\n{failed_text}\n\n"
                "<i>Пожалуйста, обратитесь в поддержку для решения вопроса.</i>",
                reply_markup=get_back_to_menu_keyboard(),
                parse_mode="HTML"
            )
            await state.clear()
        else:
            # Full failure -> auto refund
            logger.error(f"Order #{order_id} failed: {last_err}. Initiating refund...")
            await db.update_order_status(order_id, "refunded", error_message=last_err)
            refund_ok, refund_msg = await PaymentService.refund_stars(
                bot=bot,
                user_id=user_id,
                charge_id=charge_id,
                reason=last_err
            )
            await message.answer(
                f"❌ <b>Не удалось отправить подарки:</b> {last_err}\n\n"
                f"🛡️ <b>Возврат средств:</b> {refund_msg}",
                reply_markup=get_back_to_menu_keyboard(),
                parse_mode="HTML"
            )
            await state.clear()
