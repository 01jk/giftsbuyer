import logging
import asyncio
import aiohttp
from typing import Optional, Tuple
from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.exceptions import Web3Exception
from web3._utils import http_session_manager
from config import EVM_PRIVATE_KEY, POLYGON_RPC_URL, BASE_RPC_URL

logger = logging.getLogger(__name__)

# Ensure web3 aiohttp sessions use ThreadedResolver to prevent Windows aiodns DNS resolution errors
_orig_async_cache = http_session_manager.HTTPSessionManager.async_cache_and_return_session

async def _patched_async_cache(self, endpoint_uri, session=None, request_timeout=None):
    if session is None:
        session = aiohttp.ClientSession(
            raise_for_status=True,
            connector=aiohttp.TCPConnector(
                force_close=True,
                enable_cleanup_closed=True,
                resolver=aiohttp.ThreadedResolver()
            )
        )
    return await _orig_async_cache(self, endpoint_uri, session=session, request_timeout=request_timeout)

http_session_manager.HTTPSessionManager.async_cache_and_return_session = _patched_async_cache


# Standard ERC20 ABI for transfer
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

# Token contracts (Decimals = 6 for all of these)
CONTRACTS = {
    "POL_USDT": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
    "POL_USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    "BASE_USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
}

RPC_FALLBACKS = {
    "POL": [
        POLYGON_RPC_URL or "https://polygon-bor-rpc.publicnode.com",
        "https://polygon.gateway.tenderly.co",
        "https://polygon.drpc.org"
    ],
    "BASE": [
        BASE_RPC_URL or "https://mainnet.base.org",
        "https://base.gateway.tenderly.co",
        "https://base.drpc.org"
    ]
}

class Web3Service:
    def __init__(self):
        self.private_key = EVM_PRIVATE_KEY.strip() if EVM_PRIVATE_KEY else None
        
    def _create_web3(self, rpc_url: str) -> AsyncWeb3:
        w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc_url))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3
        
    async def transfer_erc20(self, network: str, currency: str, to_address: str, amount: float) -> Tuple[bool, str]:
        """
        Transfers ERC20 token to the given address.
        amount is the human-readable amount (e.g. 0.75).
        Returns (success, transaction_hash_or_error)
        """
        if not self.private_key:
            return False, "EVM_PRIVATE_KEY is not configured."
            
        contract_key = f"{network}_{currency}"
        contract_address = CONTRACTS.get(contract_key)
        if not contract_address:
            return False, f"Unsupported token {contract_key}"
            
        raw_rpcs = RPC_FALLBACKS.get(network, [])
        rpc_list = []
        for r in raw_rpcs:
            if r and r not in rpc_list:
                rpc_list.append(r)
                
        if not rpc_list:
            return False, f"No RPC configured for network {network}"

        last_err = "Failed to connect to EVM RPC node."
        for rpc_url in rpc_list:
            try:
                w3 = self._create_web3(rpc_url)
                if not await w3.is_connected():
                    continue
                return await self._execute_transfer(w3, network, contract_address, to_address, amount)
            except Exception as e:
                last_err = str(e)
                logger.warning(f"Web3 transfer via {rpc_url} failed: {e}. Trying fallback RPC...")
                continue
                
        return False, last_err

    async def _execute_transfer(self, w3: AsyncWeb3, network: str, contract_address: str, to_address: str, amount: float) -> Tuple[bool, str]:
        try:
            account = w3.eth.account.from_key(self.private_key)
            from_address = account.address
            to_address = w3.to_checksum_address(to_address)
            contract_address = w3.to_checksum_address(contract_address)
            
            contract = w3.eth.contract(address=contract_address, abi=ERC20_ABI)
            
            # Decimals = 6
            raw_amount = int(amount * 1_000_000)
            
            # Build transaction
            nonce = await w3.eth.get_transaction_count(from_address)
            
            # Get basic gas parameters based on network
            gas_params = {}
            if network == "POL":
                # Polygon uses EIP-1559 usually, get fees from oracle
                # But to be safe and simple, we can use gas_price or EIP-1559
                base_fee = (await w3.eth.get_block('latest')).get('baseFeePerGas', 0)
                if base_fee > 0:
                    gas_params['maxFeePerGas'] = int(base_fee * 1.5) + w3.to_wei(30, 'gwei')
                    gas_params['maxPriorityFeePerGas'] = w3.to_wei(30, 'gwei')
                else:
                    gas_params['gasPrice'] = await w3.eth.gas_price
            else:
                # Base is L2, standard gas price usually works fine or we use EIP1559 if available
                base_fee = (await w3.eth.get_block('latest')).get('baseFeePerGas', 0)
                if base_fee > 0:
                    gas_params['maxFeePerGas'] = int(base_fee * 1.2) + w3.to_wei(0.1, 'gwei')
                    gas_params['maxPriorityFeePerGas'] = w3.to_wei(0.1, 'gwei')
                else:
                    gas_params['gasPrice'] = await w3.eth.gas_price
            
            tx = await contract.functions.transfer(to_address, raw_amount).build_transaction({
                'from': from_address,
                'nonce': nonce,
                'gas': 100000, # Safe limit for simple ERC20 transfer
                'chainId': await w3.eth.chain_id,
                **gas_params
            })
            
            # Estimate exact gas
            try:
                estimated_gas = await w3.eth.estimate_gas(tx)
                tx['gas'] = int(estimated_gas * 1.1) # Add 10% buffer
            except Exception as e:
                logger.warning(f"Gas estimation failed, using fallback 100k limit: {e}")
            
            # Sign and send
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=self.private_key)
            raw_tx = getattr(signed_tx, "raw_transaction", getattr(signed_tx, "rawTransaction", None))
            tx_hash = await w3.eth.send_raw_transaction(raw_tx)
            
            tx_hex = w3.to_hex(tx_hash)
            
            # Wait for receipt
            receipt = await w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                return True, tx_hex
            else:
                return False, f"Transaction reverted. Hash: {tx_hex}"
                    
        except Exception as e:
            err_str = str(e)
            logger.error(f"Web3 transfer error: {err_str}")
            if "insufficient funds" in err_str or "gas required exceeds allowance" in err_str:
                from_addr_str = from_address if 'from_address' in locals() else "unknown"
                gas_token = "ETH" if network in ["BASE", "ETH"] else "POL/MATIC"
                return False, f"Недостаточно {gas_token} на мастер-кошельке ({from_addr_str}) для оплаты комиссии (газа) в сети {network}."
            return False, err_str

web3_service = Web3Service()
