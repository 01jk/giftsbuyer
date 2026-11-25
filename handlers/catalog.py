import logging
import math
from typing import Optional, List, Dict, Any
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from states.gift_states import GiftOrderState
from services.pricing_service import calculate_gift_price
from services.stickers_service import sticker_manager
from services.telethon_service import TelethonService
from services.catalog_service import catalog_service
from keyboards.common_kb import get_cancel_keyboard
from keyboards.catalog_kb import get_gift_preview_keyboard, get_catalog_keyboard, NUM_EMOJIS
from database.db import get_db

logger = logging.getLogger(__name__)
router = Router()

GIFTS_PER_PAGE = 10

async def show_catalog_page(message_or_callback: Message | CallbackQuery, state: FSMContext, page: int = 1):
    user_id = message_or_callback.from_user.id
    db = get_db()
    data = await state.get_data()
    selected_gifts: List[Dict[str, Any]] = data.get("selected_gifts", [])
    selected_ids = [g["gift_id"] for g in selected_gifts]

    gifts = await db.get_catalog_gifts(active_only=True)
    total_gifts = len(gifts)
    total_pages = math.ceil(total_gifts / GIFTS_PER_PAGE) if total_gifts > 0 else 1
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * GIFTS_PER_PAGE
    page_gifts = gifts[start_idx : start_idx + GIFTS_PER_PAGE]
    
    # Calculate price with user's markup for each gift on current page
    display_gifts = []
    for g in page_gifts:
        base_s = g.get("stars", 50)
        total_s, _, _ = await calculate_gift_price(user_id, base_s)
        g_copy = dict(g)
        g_copy["stars"] = total_s
        g_copy["base_stars"] = base_s
        display_gifts.append(g_copy)

    # Calculate total price for selected items with user markup
    total_base_stars = sum(g.get("base_stars", g.get("stars", 50)) for g in selected_gifts)
    total_user_stars, _, _ = await calculate_gift_price(user_id, total_base_stars)
    
    if selected_gifts:
        items_list = []
        for i, g in enumerate(selected_gifts):
            num = NUM_EMOJIS.get(i + 1, f"[{i+1}]")
            base_s = g.get("base_stars", g.get("stars", 50))
            item_price, _, _ = await calculate_gift_price(user_id, base_s)
            items_list.append(f"{num} <b>{g.get('title', 'Подарок')}</b> (<code>{g['gift_id']}</code>) — <b>{item_price} ⭐️</b>")
        
        items_text = "\n".join(items_list)
        text = (
            f"🛒 <b>Выбранные подарки ({len(selected_gifts)} шт.):</b>\n"
            f"<i>(Подарки будут отправлены строго в этом порядке)</i>\n\n"
            f"{items_text}\n\n"
            f"💎 <b>Итого к оплате:</b> <b>{total_user_stars} ⭐️</b>\n\n"
            f"<i>💡 Нажимайте на подарки ниже, чтобы добавить еще или убрать уже выбранные.</i>"
        )
    else:
        text = (
            "🔎 <b>Каталог скрытых и эксклюзивных подарков</b>\n\n"
            "Нажимайте на нужные подарки, чтобы добавить их в заказ по очереди. "
            "<b>Порядок выбора будет строго сохранён при доставке!</b>\n\n"
            "<i>Или отправьте мне числовой ID подарка (например: <code>6046178578163303744</code>).</i>"
        )
    
    kb = get_catalog_keyboard(
        gifts=display_gifts,
        selected_gift_ids=selected_ids,
        page=page,
        total_pages=total_pages,
        total_stars=total_user_stars
    )
    
    if isinstance(message_or_callback, CallbackQuery):
        try:
            await message_or_callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await message_or_callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message_or_callback.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "/catalog")
async def cmd_catalog(message: Message, state: FSMContext):
    await show_catalog_page(message, state, page=1)

@router.callback_query(F.data == "catalog:open")
async def cb_catalog_open(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await show_catalog_page(callback, state, page=1)

@router.callback_query(F.data.startswith("catalog:page:"))
async def cb_catalog_page(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    page = int(callback.data.split(":")[2])
    await show_catalog_page(callback, state, page=page)

@router.callback_query(F.data == "catalog:clear")
async def cb_catalog_clear(callback: CallbackQuery, state: FSMContext):
    await state.update_data(selected_gifts=[])
    try:
        await callback.answer("🗑 Выбор подарков очищен")
    except Exception:
        pass
    await show_catalog_page(callback, state, page=1)

@router.callback_query(F.data.startswith("select_gift:"))
async def cb_select_gift(callback: CallbackQuery, state: FSMContext):
    gift_id = int(callback.data.split(":")[1])
    db = get_db()
    data = await state.get_data()
    selected_gifts: List[Dict[str, Any]] = list(data.get("selected_gifts", []))
    
    existing_idx = next((i for i, g in enumerate(selected_gifts) if g["gift_id"] == gift_id), None)
    
    if existing_idx is not None:
        # Remove and keep order of remainder
        removed = selected_gifts.pop(existing_idx)
        try:
            await callback.answer(f"❌ {removed.get('title', 'Подарок')} удален из заказа")
        except Exception:
            pass
    else:
        # Fetch gift title and price
        gift_info = await db.get_catalog_gift_by_id(gift_id)
        if gift_info:
            title = gift_info.get("title") or catalog_service.get_gift_title(gift_id)
            stars = gift_info.get("stars", 50)
        else:
            title = catalog_service.get_gift_title(gift_id)
            stars = 50
            
        selected_gifts.append({
            "gift_id": gift_id,
            "title": title,
            "stars": stars,
            "base_stars": stars
        })
        pos = len(selected_gifts)
        try:
            await callback.answer(f"✅ #{pos} {title} добавлен в заказ!")
        except Exception:
            pass

    await state.update_data(selected_gifts=selected_gifts)
    await show_catalog_page(callback, state, page=1)

@router.callback_query(F.data.startswith("toggle_gift:"))
async def cb_toggle_gift(callback: CallbackQuery, state: FSMContext, bot: Bot):
    gift_id = int(callback.data.split(":")[1])
    db = get_db()
    data = await state.get_data()
    selected_gifts: List[Dict[str, Any]] = list(data.get("selected_gifts", []))
    
    existing_idx = next((i for i, g in enumerate(selected_gifts) if g["gift_id"] == gift_id), None)
    
    if existing_idx is not None:
        selected_gifts.pop(existing_idx)
        try:
            await callback.answer("❌ Удален из заказа")
        except Exception:
            pass
    else:
        gift_info = await db.get_catalog_gift_by_id(gift_id)
        if gift_info:
            title = gift_info.get("title") or catalog_service.get_gift_title(gift_id)
            stars = gift_info.get("stars", 50)
        else:
            title = catalog_service.get_gift_title(gift_id)
            stars = 50
            
        selected_gifts.append({
            "gift_id": gift_id,
            "title": title,
            "stars": stars,
            "base_stars": stars
        })
        pos = len(selected_gifts)
        try:
            await callback.answer(f"✅ Добавлен как #{pos} в заказ!")
        except Exception:
            pass

    await state.update_data(selected_gifts=selected_gifts)
    # Refresh preview card
    await show_gift_card(callback.message, bot, gift_id, state)

@router.callback_query(F.data == "input_gift_id")
async def cb_input_gift_id(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GiftOrderState.waiting_for_custom_gift_id)
    text = (
        "✏️ <b>Ввод ID скрытого подарка</b>\n\n"
        "Отправьте числовой ID подарка (например: <code>6046178578163303744</code>) в ответном сообщении.\n\n"
        "💡 <i>Найти ID любого скрытого или эксклюзивного подарка вы можете в канале: @GiftChangesIDs</i>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.message(GiftOrderState.waiting_for_custom_gift_id, F.text)
async def process_custom_gift_id(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ Пожалуйста, введите корректный числовой ID подарка (только цифры).")
        return

    gift_id = int(text)
    await show_gift_card(message, bot, gift_id, state)

# Also allow direct ID input without pressing button if message is just digits
@router.message(F.text.regexp(r"^\d{10,25}$"))
async def process_direct_gift_id(message: Message, state: FSMContext, bot: Bot):
    gift_id = int(message.text.strip())
    await show_gift_card(message, bot, gift_id, state)

async def show_gift_card(
    message: Message,
    bot: Bot,
    gift_id: int,
    state: FSMContext,
    from_user_id: int = None
):
    user_id = from_user_id or message.chat.id
    
    # 0. Immediate visual feedback
    loading_msg = await message.answer("⏳ <i>Проверяем информацию о подарке и загружаем стикер, ожидайте...</i>", parse_mode="HTML")
    
    # 1. Resolve human-readable title
    gift_title = catalog_service.get_gift_title(gift_id)

    # 2. Check gift availability and send sticker in parallel for maximum speed
    import asyncio
    check_task = asyncio.create_task(TelethonService.check_gift_availability(gift_id))
    sticker_task = asyncio.create_task(sticker_manager.send_gift_sticker(bot, chat_id=message.chat.id, gift_id=gift_id))
    
    (is_available, base_stars, status_msg), _ = await asyncio.gather(check_task, sticker_task)

    # 3. Calculate pricing for the user
    total_stars, fee_stars, is_vip = await calculate_gift_price(user_id, base_stars)

    # Remove loading notice
    try:
        await loading_msg.delete()
    except Exception:
        pass

    # Check selection status in state
    data = await state.get_data()
    selected_gifts = data.get("selected_gifts", [])
    is_selected = any(g["gift_id"] == gift_id for g in selected_gifts)

    # 5. Form text info
    vip_info = " (👑 0% для VIP)" if is_vip else f" (включая комиссию сервиса +{fee_stars} ⭐️)"
    
    header = f"🎁 <b>{gift_title}</b>\n🆔 <code>{gift_id}</code>" if not gift_title.startswith("Gift #") else f"🎁 <b>Подарок #<code>{gift_id}</code></b>"

    if is_available:
        card_text = (
            f"{header}\n\n"
            f"📊 <b>Статус:</b> {status_msg}\n"
            f"💎 <b>Базовая цена:</b> {base_stars} ⭐️\n"
            f"💰 <b>Итоговая цена:</b> <b>{total_stars} ⭐️</b>{vip_info}\n\n"
            f"<i>При отправке «С аккаунта» звёзды списываются с вашего баланса аккаунта ({base_stars} ⭐️), а в боте оплачивается только комиссия ({fee_stars} ⭐️).</i>"
        )
    else:
        card_text = (
            f"{header}\n\n"
            f"📊 <b>Статус:</b> {status_msg}\n\n"
            f"<i>К сожалению, данный подарок сейчас недоступен (распродан, завершен или указан неверный ID).</i>"
        )

    await message.answer(
        card_text,
        reply_markup=get_gift_preview_keyboard(
            gift_id=gift_id,
            is_available=is_available,
            is_selected=is_selected,
            total_selected=len(selected_gifts)
        ),
        parse_mode="HTML"
    )
