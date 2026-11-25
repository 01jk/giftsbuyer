import uuid
import time
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from states.gift_states import BuyStarsStates
from services.fragment_service import fragment_service
from services.ton_checker import ton_checker
from services.evm_checker import evm_checker
from services.exchange_service import exchange_service
from database.db import get_db
from keyboards.common_kb import get_back_to_menu_keyboard
from config import EVM_WALLET_ADDRESS
from services.web3_service import web3_service
import random

logger = logging.getLogger(__name__)
router = Router()

def get_stars_amounts_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for amount in [50, 100, 250, 500, 1000]:
        kb.button(text=f"⭐️ {amount}", callback_data=f"buy_stars_amount:{amount}")
    kb.button(text="Другое количество", callback_data="buy_stars_amount:custom")
    kb.button(text="◀️ Назад", callback_data="main_menu")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()

def get_check_payment_kb(order_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Проверить оплату", callback_data=f"check_stars_payment:{order_id}")
    kb.button(text="❌ Отмена", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()

def get_retry_fragment_kb(order_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Повторить покупку (Fragment)", callback_data=f"retry_stars_payment:{order_id}")
    kb.button(text="◀️ В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()

PAYMENT_METHOD_NAMES = {
    "TON_NATIVE": "TON (Native)",
    "TON_USDT": "USDT (TON Network)",
    "POL_USDT": "USDT (Polygon)",
    "POL_USDC": "USDC (Polygon)",
    "BASE_USDC": "USDC (Base)",
}

def get_payment_methods_kb(methods_status: dict = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if methods_status is None:
        methods_status = {k: True for k in PAYMENT_METHOD_NAMES}

    for key, label in PAYMENT_METHOD_NAMES.items():
        if methods_status.get(key, True):
            kb.button(text=label, callback_data=f"paymethod:{key}")

    kb.button(text="◀️ Назад", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()

@router.callback_query(F.data == "buy_stars_start")
async def start_buy_stars(callback: CallbackQuery, state: FSMContext):
    if not fragment_service.can_purchase:
        await callback.answer("⚠️ Сервис покупки звезд временно недоступен (не настроен).", show_alert=True)
        return

    db = get_db()
    methods_status = await db.get_payment_methods_status()
    if not any(methods_status.values()):
        await callback.answer("⚠️ Покупка звезд временно недоступна (все способы оплаты отключены).", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "⭐️ <b>Покупка Telegram Stars</b>\n\n"
        "Выберите количество звезд, которое хотите купить, или выберите 'Другое количество':",
        reply_markup=get_stars_amounts_kb(),
        parse_mode="HTML"
    )
    await state.set_state(BuyStarsStates.waiting_for_stars_amount)
    await callback.answer()

@router.callback_query(F.data.startswith("buy_stars_amount:"))
async def process_stars_amount(callback: CallbackQuery, state: FSMContext):
    amount_str = callback.data.split(":")[1]
    
    if amount_str == "custom":
        await callback.message.edit_text(
            "Введите количество звезд для покупки (от 50 до 1000000):",
            reply_markup=get_back_to_menu_keyboard()
        )
        await callback.answer()
        return

    amount = int(amount_str)
    await state.update_data(stars_amount=amount)
    await callback.message.edit_text(
        f"Вы выбрали ⭐️ <b>{amount}</b> звезд.\n\n"
        f"Введите <b>Telegram @username</b> получателя (например, @durov или просто durov):",
        reply_markup=get_back_to_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(BuyStarsStates.waiting_for_target_username)
    await callback.answer()

@router.message(BuyStarsStates.waiting_for_stars_amount)
async def process_custom_stars_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите корректное число.")
        return
        
    amount = int(message.text)
    if amount < 50 or amount > 1000000:
        await message.answer("Количество звезд должно быть от 50 до 1,000,000.")
        return
        
    await state.update_data(stars_amount=amount)
    await message.answer(
        f"Вы выбрали ⭐️ <b>{amount}</b> звезд.\n\n"
        f"Введите <b>Telegram @username</b> получателя (например, @durov или просто durov):",
        reply_markup=get_back_to_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(BuyStarsStates.waiting_for_target_username)

@router.message(BuyStarsStates.waiting_for_target_username)
async def process_target_username(message: Message, state: FSMContext):
    username = message.text.strip().replace("@", "")
    if not username:
        await message.answer("Некорректный username. Попробуйте еще раз.")
        return
        
    data = await state.get_data()
    amount = data["stars_amount"]
    
    msg = await message.answer("⏳ <i>Рассчитываем стоимость...</i>", parse_mode="HTML")
    
    ton_price = await fragment_service.get_stars_price_ton(amount, message.from_user.id)
    if ton_price is None:
        await msg.edit_text(
            "❌ Не удалось получить актуальную цену с Fragment. Попробуйте позже.",
            reply_markup=get_back_to_menu_keyboard()
        )
        return
        
    db = get_db()
    methods_status = await db.get_payment_methods_status()
    enabled_count = sum(1 for is_on in methods_status.values() if is_on)
    if enabled_count == 0:
        await msg.edit_text(
            "⚠️ В данный момент все способы оплаты временно отключены администратором.",
            reply_markup=get_back_to_menu_keyboard()
        )
        return

    await state.update_data(target_username=username, ton_price=ton_price)

    await msg.edit_text(
        f"🛒 <b>Покупка {amount} звезд для @{username}</b>\n\n"
        f"💳 Пожалуйста, выберите <b>способ оплаты</b>:",
        reply_markup=get_payment_methods_kb(methods_status),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("paymethod:"))
async def process_payment_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split(":")[1]
    db = get_db()
    if not await db.is_payment_method_enabled(method):
        await callback.answer("⚠️ Этот способ оплаты временно отключен.", show_alert=True)
        return

    data = await state.get_data()
    
    amount = data.get("stars_amount")
    username = data.get("target_username")
    ton_price = data.get("ton_price")
    
    if not amount or not username or not ton_price:
        await callback.answer("Данные сессии устарели. Начните сначала.", show_alert=True)
        return

    order_id = str(uuid.uuid4())[:8]
    memo = f"stars_{order_id}"
    
    # Defaults
    crypto_amount = ton_price
    crypto_currency = "TON"
    wallet_address = await fragment_service.get_wallet_address()
    is_evm = False
    
    if method != "TON_NATIVE":
        # Needs USDT/USDC conversion
        usd_rate = await exchange_service.get_ton_to_usd_rate()
        if not usd_rate:
            await callback.answer("Ошибка получения курса валют. Попробуйте позже.", show_alert=True)
            return
            
        crypto_amount = round(ton_price * usd_rate, 2)
        if "USDC" in method:
            crypto_currency = "USDC"
        else:
            crypto_currency = "USDT"
            
        if method != "TON_USDT":
            is_evm = True
            wallet_address = EVM_WALLET_ADDRESS
            if not wallet_address:
                await callback.answer("EVM кошелек не настроен администратором.", show_alert=True)
                return
                
            db = get_db()
            evm_fee = await db.get_evm_fee()
            crypto_amount += evm_fee
                
            # Generate unique fractional amount (e.g. 5.120485)
            fraction = random.randint(1, 9999) / 1_000_000.0
            crypto_amount = round(crypto_amount + fraction, 6)

    # Save order to DB
    db = get_db()
    await db.create_stars_order({
        "order_id": order_id,
        "user_id": callback.from_user.id,
        "target_username": username,
        "stars_amount": amount,
        "ton_price": ton_price,
        "status": "pending",
        "memo": memo,
        "payment_method": method,
        "crypto_amount": crypto_amount,
        "crypto_currency": crypto_currency
    })
    
    text = (
        f"🛒 <b>Заказ на покупку звезд</b>\n\n"
        f"⭐️ Количество: <b>{amount}</b>\n"
        f"👤 Получатель: <b>@{username}</b>\n"
        f"💳 Способ оплаты: <b>{method}</b>\n\n"
    )
    
    if is_evm:
        text += (
            f"💎 К оплате: <b>РОВНО {crypto_amount} {crypto_currency}</b>\n\n"
            f"Отправьте <b>строго указанную сумму</b> на адрес:\n"
            f"<code>{wallet_address}</code>\n\n"
            f"⚠️ <b>ВНИМАНИЕ:</b> Отправляйте ровно эту дробную сумму до последней цифры! "
            f"В сетях EVM нет поля Memo, поэтому мы определяем ваш платеж по этой уникальной сумме.\n"
        )
    else:
        text += (
            f"💎 К оплате: <b>{crypto_amount} {crypto_currency}</b>\n\n"
            f"Отправьте перевод на адрес:\n"
            f"<code>{wallet_address}</code>\n\n"
            f"📝 <b>ОБЯЗАТЕЛЬНО</b> укажите комментарий (memo) к платежу:\n"
            f"<code>{memo}</code>\n\n"
            f"⚠️ Без комментария платеж не будет засчитан!\n"
        )
        
    text += "\nПосле успешной отправки средств нажмите кнопку ниже."
    
    await callback.message.edit_text(text, reply_markup=get_check_payment_kb(order_id), parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data.startswith("check_stars_payment:"))
async def cb_check_payment(callback: CallbackQuery):
    order_id = callback.data.split(":")[1]
    
    db = get_db()
    order = await db.get_stars_order(order_id)
    
    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
        
    if order["status"] != "pending":
        await callback.answer(f"Заказ имеет статус: {order['status']}", show_alert=True)
        return
        
    # Prevent spamming
    await callback.message.edit_reply_markup(reply_markup=None)
    msg = await callback.message.reply("⏳ <i>Проверяем транзакции... это может занять несколько секунд.</i>", parse_mode="HTML")
    
    is_paid = False
    method = order.get("payment_method", "TON_NATIVE")
    crypto_amount = order.get("crypto_amount", order["ton_price"])
    
    if method == "TON_NATIVE":
        wallet_address = await fragment_service.get_wallet_address()
        is_paid = await ton_checker.check_payment(
            address=wallet_address,
            expected_amount_ton=crypto_amount,
            expected_memo=order["memo"],
            order_id=order_id
        )
    elif method == "TON_USDT":
        wallet_address = await fragment_service.get_wallet_address()
        # USDT Jetton Master on TON
        is_paid = await ton_checker.check_jetton_payment(
            address=wallet_address,
            jetton_master="EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
            expected_amount=crypto_amount,
            expected_memo=order["memo"],
            order_id=order_id
        )
    else:
        # EVM Networks
        network = method.split("_")[0] # ETH, POL, BASE
        currency = method.split("_")[1] # USDT, USDC
        is_paid = await evm_checker.check_payment(
            network=network,
            currency=currency,
            expected_amount=crypto_amount
        )
    
    if is_paid:
        # Atomic lock to prevent concurrent double-purchases
        locked = await db.try_mark_stars_order_processing(order_id)
        if not locked:
            await msg.edit_text("ℹ️ <b>Этот заказ уже обрабатывается.</b>", parse_mode="HTML")
            return

        await msg.edit_text("✅ <b>Платеж найден!</b>\n\nИнициируем покупку звезд на Fragment...", parse_mode="HTML")
        
        fragment_pay_method = "gram"
        is_evm_purchase = False
        if method == "POL_USDT":
            fragment_pay_method = "usdt_pol"
            is_evm_purchase = True
        elif method == "POL_USDC":
            fragment_pay_method = "usdc_pol"
            is_evm_purchase = True
        elif method == "BASE_USDC":
            fragment_pay_method = "usdc_base"
            is_evm_purchase = True
        
        # Call fragment
        success, tx_id_or_err, invoice = await fragment_service.purchase_stars(
            target_username=order["target_username"],
            amount=order["stars_amount"],
            payment_method=fragment_pay_method
        )
        
        if success and is_evm_purchase and invoice:
            cur_code = method.split("_")[1]
            await msg.edit_text(f"⏳ <i>Отправляем {invoice['amount']} {cur_code} в сеть {method.split('_')[0]}...</i>", parse_mode="HTML")
            net_code = method.split("_")[0]
            cur_code = method.split("_")[1]
            tx_success, tx_result = await web3_service.transfer_erc20(
                network=net_code,
                currency=cur_code,
                to_address=invoice['address'],
                amount=invoice['amount']
            )
            if tx_success:
                tx_id_or_err = tx_result
            else:
                success = False
                tx_id_or_err = f"Ошибка Web3 перевода: {tx_result}"
                
        if success:
            await db.update_stars_order_status(order_id, "completed")
            
            # Process referral reward (20% of stars markup margin)
            try:
                user_markup = await db.get_user_stars_markup(order["user_id"])
                margin_stars = int(round(order["stars_amount"] * (user_markup / 100.0)))
                from services.referral_service import referral_service
                await referral_service.process_referral_reward(
                    order_id=order_id,
                    user_id=order["user_id"],
                    margin_stars=margin_stars,
                    order_type="stars",
                    bot=callback.bot
                )
            except Exception as e:
                logger.warning(f"Error processing referral reward for stars order {order_id}: {e}")

            await msg.edit_text(
                f"🎉 <b>Успех!</b>\n\n"
                f"Звезды успешно куплены и отправлены получателю <b>@{order['target_username']}</b>!\n"
                f"ID транзакции: <code>{tx_id_or_err}</code>",
                reply_markup=get_back_to_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            await db.update_stars_order_status(order_id, "failed")
            logger.error(f"Failed to buy stars for order {order_id}: {tx_id_or_err}")
            import html
            error_text = html.escape(str(tx_id_or_err))
            await msg.edit_text(
                f"❌ <b>Ошибка при покупке звезд через Fragment:</b>\n"
                f"{error_text}\n\n"
                f"Пожалуйста, свяжитесь с администрацией или попробуйте еще раз.",
                reply_markup=get_retry_fragment_kb(order_id),
                parse_mode="HTML"
            )
    else:
        # Restore button
        await msg.delete()
        await callback.message.edit_reply_markup(reply_markup=get_check_payment_kb(order_id))
        
        network_name = "TON"
        if method.startswith("POL"):
            network_name = "Polygon"
        elif method.startswith("BASE"):
            network_name = "Base"
            
        await callback.answer(f"Платеж пока не найден. Возможно, сеть {network_name} загружена. Подождите пару минут и попробуйте снова.", show_alert=True)

@router.callback_query(F.data.startswith("retry_stars_payment:"))
async def cb_retry_stars_payment(callback: CallbackQuery):
    order_id = callback.data.split(":")[1]
    
    db = get_db()
    order = await db.get_stars_order(order_id)
    
    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
        
    if order["status"] not in ["failed", "paid"]:
        await callback.answer("Этот заказ нельзя повторить.", show_alert=True)
        return
        
    # Prevent spamming
    await callback.message.edit_reply_markup(reply_markup=None)
    msg = await callback.message.reply("⏳ <i>Повторяем попытку покупки через Fragment...</i>", parse_mode="HTML")
    
    method = order.get("payment_method", "TON_NATIVE")
    fragment_pay_method = "gram"
    is_evm_purchase = False
    if method == "POL_USDT":
        fragment_pay_method = "usdt_pol"
        is_evm_purchase = True
    elif method == "POL_USDC":
        fragment_pay_method = "usdc_pol"
        is_evm_purchase = True
    elif method == "BASE_USDC":
        fragment_pay_method = "usdc_base"
        is_evm_purchase = True
    
    # Call fragment
    success, tx_id_or_err, invoice = await fragment_service.purchase_stars(
        target_username=order["target_username"],
        amount=order["stars_amount"],
        payment_method=fragment_pay_method
    )
    
    if success and is_evm_purchase and invoice:
        cur_code = method.split("_")[1]
        await msg.edit_text(f"⏳ <i>Отправляем {invoice['amount']} {cur_code} в сеть {method.split('_')[0]}...</i>", parse_mode="HTML")
        net_code = method.split("_")[0]
        cur_code = method.split("_")[1]
        tx_success, tx_result = await web3_service.transfer_erc20(
            network=net_code,
            currency=cur_code,
            to_address=invoice['address'],
            amount=invoice['amount']
        )
        if tx_success:
            tx_id_or_err = tx_result
        else:
            success = False
            tx_id_or_err = f"Ошибка Web3 перевода: {tx_result}"
    
    if success:
        await db.update_stars_order_status(order_id, "completed")
        await msg.edit_text(
            f"🎉 <b>Успех!</b>\n\n"
            f"Звезды успешно куплены и отправлены получателю <b>@{order['target_username']}</b>!\n"
            f"ID транзакции: <code>{tx_id_or_err}</code>",
            reply_markup=get_back_to_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        # Keep status as failed
        logger.error(f"Failed to retry buy stars for order {order_id}: {tx_id_or_err}")
        await msg.edit_text(
            f"❌ <b>Ошибка при покупке звезд через Fragment:</b>\n"
            f"{tx_id_or_err}\n\n"
            f"Пожалуйста, попробуйте еще раз или свяжитесь с администрацией.",
            reply_markup=get_retry_fragment_kb(order_id),
            parse_mode="HTML"
        )
