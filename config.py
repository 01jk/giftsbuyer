import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
API_ID: int = int(os.getenv("API_ID", "0"))
API_HASH: str = os.getenv("API_HASH", "")

# Admin IDs
raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [
    int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()
]

# Markup percentage
DEFAULT_MARKUP_PERCENT: float = float(os.getenv("DEFAULT_MARKUP_PERCENT", "30.0"))

# Sticker pack
STICKER_SET_NAME: str = os.getenv("STICKER_SET_NAME", "gifts_1_by_gifts_changes_bot")

# Master session name for sending gifts without user login
BOT_MASTER_SESSION: str = os.getenv("BOT_MASTER_SESSION", "session_gift_test")

# Fragment & TON Settings
FRAGMENT_COOKIES: str = os.getenv("FRAGMENT_COOKIES", "")
FRAGMENT_SEED: str = os.getenv("FRAGMENT_SEED", "")
TONCONSOLE_API_KEY: str = os.getenv("TONCONSOLE_API_KEY", "")
TONAPI_KEY: str = os.getenv("TONAPI_KEY", "")

EVM_WALLET_ADDRESS: str = os.getenv("EVM_WALLET_ADDRESS", "")
EVM_PRIVATE_KEY: str = os.getenv("EVM_PRIVATE_KEY", "")
ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "")
POLYGONSCAN_API_KEY: str = os.getenv("POLYGONSCAN_API_KEY", "")
BASESCAN_API_KEY: str = os.getenv("BASESCAN_API_KEY", "")

ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "https://eth.drpc.org")
POLYGON_RPC_URL: str = os.getenv("POLYGON_RPC_URL", "https://polygon-bor-rpc.publicnode.com")
BASE_RPC_URL: str = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")

# Markup percentage for Stars sales
STARS_MARKUP_PERCENT: float = float(os.getenv("STARS_MARKUP_PERCENT", "20.0"))

# Database path
DB_PATH: str = os.getenv("DB_PATH", "/data/gifts_buyer.db")
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    try:
        os.makedirs(db_dir, exist_ok=True)
    except Exception:
        pass

# Optional Proxy (e.g. http://user:pass@host:port or socks5://host:port)
PROXY: str = os.getenv("PROXY", "").strip() or None
