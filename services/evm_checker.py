import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from config import EVM_WALLET_ADDRESS, ETH_RPC_URL, BASE_RPC_URL, POLYGON_RPC_URL

logger = logging.getLogger(__name__)

# Token contracts (Decimals = 6 for all of these)
CONTRACTS = {
    "ETH_USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "ETH_USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "POL_USDT": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
    "POL_USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    "BASE_USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
}

DECIMALS = {
    "ETH_USDT": 6,
    "ETH_USDC": 6,
    "POL_USDT": 6,
    "POL_USDC": 6,
    "BASE_USDC": 6
}

# Reliable RPC Endpoints with fallbacks for each network
RPC_ENDPOINTS: Dict[str, List[str]] = {
    "BASE": [
        BASE_RPC_URL or "https://mainnet.base.org",
        "https://base.gateway.tenderly.co",
        "https://base.drpc.org",
        "https://base-rpc.publicnode.com"
    ],
    "POL": [
        POLYGON_RPC_URL or "https://polygon-bor-rpc.publicnode.com",
        "https://polygon.gateway.tenderly.co",
        "https://polygon.drpc.org"
    ],
    "ETH": [
        ETH_RPC_URL or "https://eth.drpc.org",
        "https://gateway.tenderly.co/public/mainnet",
        "https://ethereum.publicnode.com"
    ]
}

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

class EVMCheckerService:
    def __init__(self):
        self.wallet_address = EVM_WALLET_ADDRESS.strip().lower() if EVM_WALLET_ADDRESS else None

    async def _rpc_call(self, network: str, method: str, params: list) -> Optional[Any]:
        """Makes an RPC call with fallback across multiple nodes."""
        raw_endpoints = RPC_ENDPOINTS.get(network, [])
        endpoints = []
        for ep in raw_endpoints:
            if ep and ep not in endpoints:
                endpoints.append(ep)
        if not endpoints:
            return None

        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async with aiohttp.ClientSession(connector=connector) as session:
            for url in endpoints:
                try:
                    payload = {
                        "jsonrpc": "2.0",
                        "method": method,
                        "params": params,
                        "id": 1
                    }
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if "result" in data:
                                return data["result"]
                            elif "error" in data:
                                logger.debug(f"RPC error from {url}: {data['error']}")
                except Exception as e:
                    logger.debug(f"RPC endpoint {url} failed: {e}")
                    continue
        return None

    async def check_payment(self, network: str, currency: str, expected_amount: float) -> bool:
        """
        Checks if the exact `expected_amount` has been received in the specified network and currency
        by querying blockchain transfer logs directly via RPC nodes.
        `network` should be 'ETH', 'POL', or 'BASE'.
        `currency` should be 'USDT' or 'USDC'.
        """
        if not self.wallet_address:
            logger.error("EVM_WALLET_ADDRESS is not set. Cannot check payment.")
            return False
            
        contract_key = f"{network}_{currency}"
        contract_address = CONTRACTS.get(contract_key)
        if not contract_address:
            logger.error(f"Unsupported contract for network {network} and currency {currency}.")
            return False
            
        decimals = DECIMALS.get(contract_key, 6)
        expected_raw_amount = int(round(expected_amount * (10 ** decimals)))
        
        # Topic for to_address (32 bytes zero-padded)
        clean_addr = self.wallet_address.replace("0x", "").zfill(64)
        topic_to = "0x" + clean_addr
        
        try:
            # 1. Get latest block number
            block_hex = await self._rpc_call(network, "eth_blockNumber", [])
            if not block_hex:
                logger.error(f"Failed to get block number from RPC for {network}")
                return False
                
            latest_block = int(block_hex, 16)
            
            # Base/Polygon ~2s block time: 5000 blocks ≈ 2.7 hours
            # Ethereum ~12s block time: 1000 blocks ≈ 3.3 hours
            block_delta = 1000 if network == "ETH" else 5000
            from_block = hex(max(0, latest_block - block_delta))
            
            # 2. Get ERC20 Transfer logs
            logs = await self._rpc_call(network, "eth_getLogs", [{
                "fromBlock": from_block,
                "toBlock": "latest",
                "address": contract_address,
                "topics": [
                    TRANSFER_TOPIC,
                    None,      # from any
                    topic_to   # to our wallet
                ]
            }])
            
            if logs is None:
                logger.error(f"Failed to fetch logs from RPC for {network}")
                return False
                
            for log in logs:
                data_hex = log.get("data", "0x0")
                raw_amt = int(data_hex, 16)
                
                # Allow +/- 1 unit tolerance for potential floating-point rounding
                if abs(raw_amt - expected_raw_amount) <= 1:
                    logger.info(f"Verified EVM payment on {network} {currency}: {expected_amount} (tx: {log.get('transactionHash')})")
                    return True
                    
            logger.info(f"Payment {expected_amount} {currency} on {network} not found in recent blocks.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking EVM payment on {network}: {e}")
            return False

    async def get_balances(self) -> dict:
        """Returns a dict of balances like {'BASE_USDC': 1.5, 'POL_USDT': 2.0, ...}"""
        balances = {}
        if not self.wallet_address:
            return balances

        clean_addr = self.wallet_address.replace("0x", "").zfill(64)
        # balanceOf selector: 0x70a08231 + padded address
        call_data = "0x70a08231" + clean_addr
        
        tasks = []
        keys = []
        
        for network in ["BASE", "POL", "ETH"]:
            for currency in ["USDT", "USDC"]:
                contract_key = f"{network}_{currency}"
                if contract_key in CONTRACTS:
                    contract_address = CONTRACTS[contract_key]
                    tasks.append(self._rpc_call(network, "eth_call", [{"to": contract_address, "data": call_data}, "latest"]))
                    keys.append((contract_key, DECIMALS.get(contract_key, 6)))
        
        results = await asyncio.gather(*tasks)
        for (key, dec), res in zip(keys, results):
            if res:
                try:
                    balances[key] = int(res, 16) / (10 ** dec)
                except Exception:
                    pass
                    
        return balances

evm_checker = EVMCheckerService()

