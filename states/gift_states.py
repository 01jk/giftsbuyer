from aiogram.fsm.state import State, StatesGroup

class GiftOrderState(StatesGroup):
    waiting_for_custom_gift_id = State()
    waiting_for_recipient = State()
    waiting_for_channel_manual = State()
    waiting_for_signature = State()

class BuyStarsStates(StatesGroup):
    waiting_for_stars_amount = State()
    waiting_for_target_username = State()
    waiting_for_payment = State()

class AdminState(StatesGroup):
    waiting_for_vip_id = State()
    waiting_for_remove_vip_id = State()
    waiting_for_markup = State()
    waiting_for_gift_id = State()
    waiting_for_gift_title = State()
    waiting_for_gift_price = State()
    waiting_for_remove_gift_id = State()
    waiting_for_refund_data = State()
    waiting_for_stars_markup = State()
    waiting_for_evm_fee = State()

class PartnerWithdrawState(StatesGroup):
    waiting_for_address = State()
    waiting_for_memo = State()

class PartnerApplicationState(StatesGroup):
    waiting_for_note = State()

class SupportState(StatesGroup):
    waiting_for_message = State()

class AdminSupportReplyState(StatesGroup):
    waiting_for_reply = State()

class AdminPartnerState(StatesGroup):
    waiting_for_partner_search = State()
    waiting_for_gift_markup = State()
    waiting_for_stars_markup = State()
    waiting_for_custom_days = State()
    waiting_for_promo_code = State()

class AdminApplicationDecisionState(StatesGroup):
    waiting_for_duration_days = State()
    waiting_for_gift_markup = State()
    waiting_for_stars_markup = State()
    waiting_for_comment = State()
    waiting_for_reject_reason = State()

class AdminWithdrawalDecisionState(StatesGroup):
    waiting_for_reject_reason = State()

class AdminBroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirm = State()

class AdminPromoCreateState(StatesGroup):
    waiting_for_code = State()
    waiting_for_name = State()
    waiting_for_gift_markup = State()
    waiting_for_stars_markup = State()
    waiting_for_duration = State()

class AdminPromoEditState(StatesGroup):
    waiting_for_gift_markup = State()
    waiting_for_stars_markup = State()
    waiting_for_duration = State()
