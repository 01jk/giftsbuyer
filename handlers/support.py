import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
from states.gift_states import SupportState, AdminSupportReplyState
from keyboards.support_kb import (
    get_support_user_kb,
    get_support_admin_reply_kb,
    get_support_admin_cancel_kb
)
from keyboards.common_kb import get_back_to_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("support"))
@router.callback_query(F.data == "support:open")
async def cb_support_open(event: Message | CallbackQuery, state: FSMContext):
    await state.set_state(SupportState.waiting_for_message)
    text = (
        "💬 <b>Связь с администрацией</b>\n\n"
        "Напишите ваш вопрос, проблему или предложение прямо в этот чат.\n"
        "Администратор ответит вам в ближайшее время!"
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=get_support_user_kb(), parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=get_support_user_kb(), parse_mode="HTML")


@router.message(SupportState.waiting_for_message, F.text)
async def process_user_support_message(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Пользователь"
    user_text = message.text.strip()
    await state.clear()

    await message.answer(
        "✅ <b>Ваше сообщение отправлено администрации!</b>\n\n"
        "Ожидайте ответа в этом чате.",
        reply_markup=get_back_to_menu_keyboard(),
        parse_mode="HTML"
    )

    user_label = f"@{username}" if username else f"{first_name} (ID: <code>{user_id}</code>)"
    admin_msg = (
        "📩 <b>Новое обращение в поддержку!</b>\n\n"
        f"👤 <b>От:</b> {user_label} (<code>{user_id}</code>)\n\n"
        f"💬 <b>Сообщение:</b>\n{user_text}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_msg,
                reply_markup=get_support_admin_reply_kb(user_id),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not send support message to admin {admin_id}: {e}")


@router.callback_query(F.data.startswith("support:reply:"))
async def cb_admin_support_reply_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    target_user_id = int(callback.data.split(":")[2])
    await state.set_state(AdminSupportReplyState.waiting_for_reply)
    await state.update_data(support_target_user_id=target_user_id)

    await callback.message.reply(
        f"✍️ Введите <b>текст ответа</b> для пользователя <code>{target_user_id}</code>:",
        reply_markup=get_support_admin_cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminSupportReplyState.waiting_for_reply, F.text)
async def process_admin_support_reply(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    target_user_id = data.get("support_target_user_id")
    reply_text = message.text.strip()
    await state.clear()

    if not target_user_id:
        await message.answer("⚠️ Ошибка: получатель ответа не найден.")
        return

    try:
        user_msg = (
            "👨‍💻 <b>Ответ от службы поддержки:</b>\n\n"
            f"{reply_text}\n\n"
            "<i>Чтобы отправить новое сообщение, воспользуйтесь разделом «💬 Поддержка».</i>"
        )
        await bot.send_message(chat_id=target_user_id, text=user_msg, parse_mode="HTML")
        await message.answer(f"✅ Ответ успешно доставлен пользователю <code>{target_user_id}</code>!")
    except Exception as e:
        await message.answer(f"❌ Не удалось доставить ответ пользователю <code>{target_user_id}</code>: {e}")
