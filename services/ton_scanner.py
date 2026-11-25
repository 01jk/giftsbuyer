import asyncio
import logging
from typing import Optional, Dict, Any
import aiohttp
from pytoniq import LiteClient
from pytoniq_core import Slice, Cell, Address
from database import get_db
from services.fragment_service import fragment_service

logger = logging.getLogger("TonScanner")
logging.getLogger("LiteClient").setLevel(logging.WARNING)

class TonScannerService:
    def __init__(self):
        self.client: Optional[LiteClient] = None
        self._is_running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._cached_address: Optional[str] = None
        self._config: Optional[dict] = None
        self._current_ls_index = 0

    async def _get_global_config(self) -> Optional[dict]:
        if self._config:
            return self._config

        try:
            connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get("https://ton.org/global-config.json", timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status == 200:
                        self._config = await resp.json()
                        return self._config
        except Exception as e:
            logger.debug(f"Failed to fetch TON global-config asynchronously: {e}")

        return None

    async def _ensure_client(self) -> Optional[LiteClient]:
        async with self._lock:
            if self.client is not None and self.client.inited:
                return self.client

            config = await self._get_global_config()
            total_nodes = len(config.get("liteservers", [])) if config else 10

            try:
                logger.info(f"Connecting to TON LiteServer node #{self._current_ls_index}...")
                if config:
                    self.client = LiteClient.from_config(config, ls_i=self._current_ls_index, trust_level=1, timeout=6)
                else:
                    self.client = LiteClient.from_mainnet_config(ls_i=self._current_ls_index, trust_level=1, timeout=6)
                
                await self.client.connect()
                logger.info(f"Connected to TON LiteServer #{self._current_ls_index} successfully.")
            except Exception as e:
                logger.warning(f"Failed to connect to LiteServer #{self._current_ls_index}: {e}. Switching to next node...")
                self._current_ls_index = (self._current_ls_index + 1) % max(1, total_nodes)
                self.client = None

            return self.client

    def _parse_in_msg(self, in_msg) -> Optional[Dict[str, Any]]:
        """
        Extracts payment details (amount, memo/comment, currency, sender) from in_msg.
        Supports native TON transfers and Jetton transfer_notifications (USDT).
        """
        if not in_msg or not in_msg.body:
            return None

        try:
            cs: Slice = in_msg.body.begin_parse()
            if cs.remaining_bits >= 32:
                op = cs.load_uint(32)
                
                # 1. Native TON comment (opcode 0x00000000)
                if op == 0:
                    comment = cs.load_snake_string() if cs.remaining_bits > 0 else ""
                    sender_addr = str(in_msg.info.src) if in_msg.info and in_msg.info.src else None
                    amount_ton = float(in_msg.info.value_coins) / 1e9 if in_msg.info else 0.0
                    return {
                        "currency": "TON",
                        "amount": round(amount_ton, 9),
                        "memo": comment.strip() if comment else None,
                        "sender": sender_addr
                    }
                    
                # 2. Jetton transfer_notification (opcode 0x7362d09c)
                elif op == 0x7362d09c:
                    query_id = cs.load_uint(64)
                    jetton_amount_raw = cs.load_coins()
                    sender = cs.load_address()
                    
                    # Forward payload can be either directly in slice or in ref
                    forward_payload = cs
                    if forward_payload.remaining_bits > 0 and forward_payload.load_bit() == 1:
                        if forward_payload.remaining_refs > 0:
                            forward_payload = forward_payload.load_ref().begin_parse()
                    
                    jetton_comment = ""
                    if forward_payload.remaining_bits >= 32:
                        fwd_op = forward_payload.load_uint(32)
                        if fwd_op == 0:
                            jetton_comment = forward_payload.load_snake_string()
                            
                    # For USDT, 6 decimals
                    jetton_amount = float(jetton_amount_raw) / 1e6
                    
                    return {
                        "currency": "USDT",
                        "amount": round(jetton_amount, 6),
                        "memo": jetton_comment.strip() if jetton_comment else None,
                        "sender": str(sender) if sender else None
                    }
        except Exception as e:
            logger.debug(f"Error parsing in_msg: {e}")

        return None

    async def get_target_address(self) -> Optional[str]:
        if not self._cached_address:
            try:
                self._cached_address = await fragment_service.get_wallet_address()
            except Exception as e:
                logger.warning(f"Could not get target wallet address: {e}")
        return self._cached_address

    async def _safe_get_transactions(self, client: LiteClient, address: str, shard_account, desired_count: int = 20):
        for cnt in [desired_count, 10, 5, 3, 1]:
            try:
                return await client.get_transactions(
                    address=address,
                    count=cnt,
                    from_lt=shard_account.last_trans_lt,
                    from_hash=shard_account.last_trans_hash
                )
            except Exception as e:
                if "specified logical time" in str(e) or "-400" in str(e):
                    continue
                raise e
        return []

    async def sync_once(self) -> int:
        """
        Performs one scan pass on the target wallet.
        Returns the number of newly discovered transactions.
        """
        address = await self.get_target_address()
        if not address:
            return 0

        client = await self._ensure_client()
        if not client:
            return 0

        db = get_db()
        last_lt = await db.get_last_scanned_ton_lt()
        new_count = 0
        max_lt_seen = last_lt

        try:
            # 1. Fetch current account state
            account, shard_account = await client.raw_get_account_state(address=address)
            if not shard_account or not shard_account.last_trans_lt or shard_account.last_trans_lt == 0:
                return 0

            # If no new transactions since last scanned LT, return immediately
            if last_lt > 0 and shard_account.last_trans_lt <= last_lt:
                return 0

            # 2. Fetch latest transactions safely
            txs = await self._safe_get_transactions(client, address, shard_account, desired_count=20)

            for tx in txs:
                tx_lt = tx.lt
                max_lt_seen = max(max_lt_seen, tx_lt)

                tx_hash = tx.cell.hash.hex()
                parsed = self._parse_in_msg(tx.in_msg)
                
                if parsed and parsed.get("amount", 0) > 0:
                    tx_record = {
                        "tx_hash": tx_hash,
                        "lt": tx_lt,
                        "currency": parsed["currency"],
                        "amount": parsed["amount"],
                        "memo": parsed.get("memo"),
                        "sender": parsed.get("sender")
                    }
                    inserted = await db.save_received_ton_tx(tx_record)
                    if inserted:
                        new_count += 1
                        logger.info(
                            f"Saved new TON payment tx: {tx_hash[:10]}... | "
                            f"{parsed['amount']} {parsed['currency']} | Memo: '{parsed.get('memo')}'"
                        )

            if max_lt_seen > last_lt:
                await db.set_last_scanned_ton_lt(max_lt_seen)

        except Exception as e:
            logger.warning(f"Error during TON scan pass on node #{self._current_ls_index}: {e}")
            total_nodes = len(self._config.get("liteservers", [])) if self._config else 10
            self._current_ls_index = (self._current_ls_index + 1) % max(1, total_nodes)
            if self.client:
                try:
                    await self.client.close()
                except Exception:
                    pass
            self.client = None

        return new_count

    async def _scanner_loop(self):
        logger.info("TON background scanner loop started.")
        while self._is_running:
            try:
                await self.sync_once()
            except Exception as e:
                logger.error(f"Unexpected error in TON scanner loop: {e}")

            await asyncio.sleep(2.5)

    def start(self):
        if not self._is_running:
            self._is_running = True
            self._task = asyncio.create_task(self._scanner_loop())
            logger.info("TonScanner background service launched.")

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass
            self.client = None
        logger.info("TonScanner service stopped.")

ton_scanner = TonScannerService()
