import math
from typing import Tuple
from database import get_db

async def calculate_gift_price(user_id: int, base_stars: int, db=None) -> Tuple[int, int, bool]:
    """
    Returns (total_stars, fee_stars, is_vip)
    """
    if db is None:
        db = get_db()
    is_vip = await db.is_vip(user_id)
    
    if is_vip:
        return base_stars, 0, True
    
    markup_percent = await db.get_user_gift_markup(user_id)
    fee_stars = math.ceil(base_stars * (markup_percent / 100.0))
    if fee_stars < 1 and markup_percent > 0:
        fee_stars = 1
    total_stars = base_stars + fee_stars
    return total_stars, fee_stars, False
