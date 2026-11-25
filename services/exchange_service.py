import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

class ExchangeService:
    def __init__(self):
        self.api_url = "https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT"
        
    async def get_ton_to_usd_rate(self) -> Optional[float]:
        """
        Fetches the current TON to USDT exchange rate from Binance.
        """
        try:
            connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(self.api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data["price"])
                    else:
                        logger.error(f"Failed to fetch exchange rate from Binance: {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching exchange rate: {e}")
            return None

exchange_service = ExchangeService()
