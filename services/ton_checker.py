import logging
import aiohttp
from typing import Optional
from config import TONAPI_KEY
from database import get_db
from services.ton_scanner import ton_scanner

logger = logging.getLogger(__name__)

class TonCheckerService:
    def __init__(self):
        self.api_key = TONAPI_KEY.strip() if TONAPI_KEY else None

    async def check_payment(
        self,
        address: str,
        expected_amount_ton: float,
        expected_memo: str,
        order_id: str = ""
    ) -> bool:
        """
        Checks if the wallet received a TON transfer with the given memo and amount.
        1. Instant check against local SQLite cache (0ms, 0 external RPS).
        2. If not found, forces an on-demand sync from LiteServers.
        3. Fallback to TonAPI if configured and still not found.
        """
        db = get_db()
        
        # Step 1: Fast local DB check
        if await db.claim_received_ton_tx(memo=expected_memo, expected_amount=expected_amount_ton, order_id=order_id, currency="TON"):
            logger.info(f"Payment matched instantly in local DB for memo: '{expected_memo}'")
            return True

        # Step 2: Force on-demand scan pass via PyTonIQ LiteServers
        try:
            await ton_scanner.sync_once()
            if await db.claim_received_ton_tx(memo=expected_memo, expected_amount=expected_amount_ton, order_id=order_id, currency="TON"):
                logger.info(f"Payment matched after LiteServer sync for memo: '{expected_memo}'")
                return True
        except Exception as e:
            logger.warning(f"Error during on-demand LiteServer check: {e}")

        # Step 3: Optional TonAPI fallback
        if self.api_key:
            try:
                expected_nanoton = int(expected_amount_ton * 1e9)
                url = f"https://tonapi.io/v2/accounts/{address}/events"
                headers = {"Authorization": f"Bearer {self.api_key}"}

                connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(url, headers=headers, params={"limit": 20}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for event in data.get("events", []):
                                for action in event.get("actions", []):
                                    if action.get("type") == "TonTransfer":
                                        transfer = action.get("TonTransfer", {})
                                        memo = transfer.get("comment", "")
                                        amount = int(transfer.get("amount", 0))

                                        if memo and memo.strip() == expected_memo.strip():
                                            if amount >= expected_nanoton:
                                                tx_hash = event.get("event_id", f"tonapi_{expected_memo}")
                                                # Save and claim in DB
                                                await db.save_received_ton_tx({
                                                    "tx_hash": tx_hash,
                                                    "lt": event.get("lt", 0),
                                                    "currency": "TON",
                                                    "amount": amount / 1e9,
                                                    "memo": memo,
                                                    "sender": transfer.get("sender", {}).get("address")
                                                })
                                                return await db.claim_received_ton_tx(memo=expected_memo, expected_amount=expected_amount_ton, order_id=order_id, currency="TON")
            except Exception as ex:
                logger.debug(f"TonAPI fallback error: {ex}")

        return False

    async def check_jetton_payment(
        self,
        address: str,
        jetton_master: str,
        expected_amount: float,
        expected_memo: str,
        decimals: int = 6,
        order_id: str = ""
    ) -> bool:
        """
        Checks if the wallet received a Jetton (e.g. USDT) transfer with given memo and amount.
        """
        db = get_db()

        # Step 1: Fast local DB check
        if await db.claim_received_ton_tx(memo=expected_memo, expected_amount=expected_amount, order_id=order_id, currency="USDT"):
            logger.info(f"USDT Payment matched instantly in local DB for memo: '{expected_memo}'")
            return True

        # Step 2: Force on-demand scan pass via PyTonIQ LiteServers
        try:
            await ton_scanner.sync_once()
            if await db.claim_received_ton_tx(memo=expected_memo, expected_amount=expected_amount, order_id=order_id, currency="USDT"):
                logger.info(f"USDT Payment matched after LiteServer sync for memo: '{expected_memo}'")
                return True
        except Exception as e:
            logger.warning(f"Error during on-demand USDT LiteServer check: {e}")

        # Step 3: Optional TonAPI fallback
        if self.api_key:
            try:
                expected_raw = int(expected_amount * (10 ** decimals))
                url = f"https://tonapi.io/v2/accounts/{address}/jettons/{jetton_master}/history"
                headers = {"Authorization": f"Bearer {self.api_key}"}

                connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(url, headers=headers, params={"limit": 20}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for event in data.get("events", []):
                                for action in event.get("actions", []):
                                    if action.get("type") == "JettonTransfer":
                                        transfer = action.get("JettonTransfer", {})
                                        memo = transfer.get("comment", "")
                                        amount = int(transfer.get("amount", 0))

                                        if memo and memo.strip() == expected_memo.strip():
                                            if amount >= expected_raw:
                                                tx_hash = event.get("event_id", f"tonapi_{expected_memo}")
                                                await db.save_received_ton_tx({
                                                    "tx_hash": tx_hash,
                                                    "lt": event.get("lt", 0),
                                                    "currency": "USDT",
                                                    "amount": amount / (10 ** decimals),
                                                    "memo": memo,
                                                    "sender": transfer.get("sender", {}).get("address")
                                                })
                                                return await db.claim_received_ton_tx(memo=expected_memo, expected_amount=expected_amount, order_id=order_id, currency="USDT")
            except Exception as ex:
                logger.debug(f"TonAPI Jetton fallback error: {ex}")

        return False

    async def get_balances(self, address: str) -> dict:
        """Returns {'TON': x, 'USDT': y}"""
        balances = {"TON": 0.0, "USDT": 0.0}
        if not self.api_key:
            return balances

        headers = {"Authorization": f"Bearer {self.api_key}"}
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async with aiohttp.ClientSession(connector=connector) as session:
            # Get TON
            try:
                async with session.get(f"https://tonapi.io/v2/accounts/{address}", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        balances["TON"] = float(data.get("balance", 0)) / 1_000_000_000.0
            except:
                pass

            # Get USDT
            try:
                jetton_master = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
                async with session.get(f"https://tonapi.io/v2/accounts/{address}/jettons/{jetton_master}", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        balances["USDT"] = float(data.get("balance", 0)) / 1_000_000.0
            except:
                pass

        return balances

ton_checker = TonCheckerService()
