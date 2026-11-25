from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Any, Optional

NUM_EMOJIS = {
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣",
    6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"
}

def get_catalog_keyboard(
    gifts: List[Dict[str, Any]],
    selected_gift_ids: Optional[List[int]] = None,
    page: int = 1,
    total_pages: int = 1,
    total_stars: int = 0
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    selected_ids = selected_gift_ids or []
    
    # 2-column layout for gifts
    for i in range(0, len(gifts), 2):
        row_buttons = []
        for g in gifts[i:i+2]:
            gift_id = g["gift_id"]
            stars = g.get("stars", 0)
            emoji_id = g.get("emoji_id")
            
            if gift_id in selected_ids:
                pos = selected_ids.index(gift_id) + 1
                badge = NUM_EMOJIS.get(pos, f"[{pos}]")
                btn_text = f"{badge} | {stars} ⭐️"
            else:
                btn_text = f"| {stars} ⭐️" if emoji_id else f"🎁 | {stars} ⭐️"
            
            kwargs = {
                "text": btn_text,
                "callback_data": f"select_gift:{gift_id}"
            }
            if emoji_id:
                kwargs["icon_custom_emoji_id"] = str(emoji_id)
                
            row_buttons.append(InlineKeyboardButton(**kwargs))
            
        kb.row(*row_buttons)
    
    # Action buttons when items are selected
    if selected_ids:
        count = len(selected_ids)
        stars_suffix = f" • {total_stars} ⭐️" if total_stars > 0 else ""
        kb.row(InlineKeyboardButton(
            text=f"✨ Оформить заказ ({count} шт.{stars_suffix})",
            callback_data="catalog:checkout"
        ))
        kb.row(
            InlineKeyboardButton(text="🗑 Очистить выбор", callback_data="catalog:clear"),
            InlineKeyboardButton(text="✏️ Ввести ID", callback_data="input_gift_id")
        )
    else:
        kb.row(InlineKeyboardButton(text="✏️ Ввести ID вручную", callback_data="input_gift_id"))

    # Pagination
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"catalog:page:{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"catalog:page:{page+1}"))
        
    if nav_buttons:
        kb.row(*nav_buttons)

    kb.row(InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu"))
    return kb.as_markup()

def get_gift_preview_keyboard(
    gift_id: int,
    is_available: bool = True,
    is_selected: bool = False,
    total_selected: int = 0
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if is_available:
        if is_selected:
            kb.button(text="➖ Убрать из заказа", callback_data=f"toggle_gift:{gift_id}")
        else:
            kb.button(text="➕ Добавить в заказ", callback_data=f"toggle_gift:{gift_id}")
            
        kb.button(text="💳 Купить сразу только этот", callback_data=f"buy_gift:{gift_id}")
        
        if total_selected > 0:
            kb.button(text=f"✨ Оформить все выбранные ({total_selected} шт.)", callback_data="catalog:checkout")
            
    kb.button(text="◀️ Назад в каталог", callback_data="catalog:open")
    kb.button(text="◀️ В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


