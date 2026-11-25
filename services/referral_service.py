import logging
from typing import Optional
from aiogram import Bot
from database import get_db

logger = logging.getLogger(__name__)

class ReferralService:
    @staticmethod
    async def process_referral_reward(
        order_id: str,
        user_id: int,
        margin_stars: int,
        order_type: str, # 'gift' or 'stars'
        bot: Optional[Bot] = None
    ) -> Optional[int]:
        """
        Checks if buyer has a referrer. If referrer is an active partner and margin_stars > 0:
        Calculates 20% margin in Stars, credits partner's balance, and notifies partner.
        Returns earned_stars or None.
        """
        if margin_stars <= 0:
            return None

        db = get_db()
        user = await db.get_user(user_id)
        if not user:
            return None

        referrer_id = user.get("referrer_id")
        if not referrer_id or referrer_id == user_id:
            return None

        # Check if referrer exists and has partner status (or not expired)
        referrer = await db.get_user(referrer_id)
        if not referrer or not referrer.get("is_partner"):
            return None

        # Check if partner program is expired
        if not await db.is_active_partner(referrer_id):
            logger.info(f"Referrer {referrer_id} partner program is expired, skipping reward.")
            return None

        # 20% of margin
        earned_stars = int(round(margin_stars * 0.20))
        if earned_stars < 1 and margin_stars >= 1:
            earned_stars = 1

        if earned_stars <= 0:
            return None

        new_balance = await db.add_partner_reward(
            partner_id=referrer_id,
            referral_id=user_id,
            order_id=order_id,
            order_type=order_type,
            margin_stars=margin_stars,
            earned_stars=earned_stars
        )

        logger.info(
            f"Credited {earned_stars} ⭐️ (20% of {margin_stars} margin) to partner {referrer_id} "
            f"for {order_type} order {order_id} by referral {user_id}. New balance: {new_balance} ⭐️"
        )

        # Notify partner in Telegram
        if bot:
            try:
                referral_name = user.get("username")
                ref_label = f"@{referral_name}" if referral_name else f"ID: {user_id}"
                type_label = "покупку подарка" if order_type == "gift" else "покупку Telegram Stars"

                text = (
                    "⭐️ <b>Начисление по партнерской программе!</b>\n\n"
                    f"Ваш реферал ({ref_label}) совершил {type_label}.\n"
                    f"💰 Вам начислено 20% маржи: <b>+{earned_stars} ⭐️</b>\n"
                    f"💼 Ваш текущий партнерский баланс: <b>{new_balance} ⭐️</b>\n\n"
                    f"<i>Проверить баланс и статистику можно в разделе «🤝 Партнерская программа».</i>"
                )
                await bot.send_message(chat_id=referrer_id, text=text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Could not send reward notification to partner {referrer_id}: {e}")

        return earned_stars

referral_service = ReferralService()
