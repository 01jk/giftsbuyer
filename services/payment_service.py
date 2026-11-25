import logging
from typing import Optional, Tuple
from aiogram import Bot
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import get_db

logger = logging.getLogger(__name__)

class PaymentService:
    @staticmethod
    def create_invoice_keyboard(stars: int) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        kb.button(text=f"⭐️ Оплатить {stars} XTR", pay=True)
        kb.button(text="❌ Отменить", callback_data="cancel_order")
        kb.adjust(1)
        return kb.as_markup()

    @staticmethod
    async def refund_stars(
        bot: Bot,
        user_id: int,
        charge_id: str,
        reason: str = "Ошибка выполнения заказа"
    ) -> Tuple[bool, str]:
        """
        Executes a Star refund using Telegram Bot API.
        """
        if not charge_id:
            return False, "Отсутствует ID транзакции для возврата."
        
        try:
            await bot.refund_star_payment(
                user_id=user_id,
                telegram_payment_charge_id=charge_id
            )
            logger.info(f"Successfully refunded {charge_id} to user {user_id}. Reason: {reason}")
            return True, "Звёзды были успешно возвращены на ваш баланс!"
        except Exception as e:
            logger.error(f"Failed to refund stars for {user_id} (charge_id: {charge_id}): {e}")
            return False, f"Ошибка возврата звёзд: {e}"
