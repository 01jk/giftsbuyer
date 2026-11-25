import os
import shutil
import aiosqlite
import datetime
from typing import Optional, List, Dict, Any
from config import DB_PATH, DEFAULT_MARKUP_PERCENT, STARS_MARKUP_PERCENT

from database.default_catalog import DEFAULT_CATALOG_GIFTS

class Database:
    def __init__(self, db_path: str = DB_PATH):

        self.db_path = db_path
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception:
                pass
        
        # If the target DB does not exist yet, check if a legacy 'gifts_buyer.db' exists in current dir to migrate
        if not os.path.exists(self.db_path) and os.path.exists("gifts_buyer.db") and os.path.abspath(self.db_path) != os.path.abspath("gifts_buyer.db"):
            try:
                shutil.copy2("gifts_buyer.db", self.db_path)
            except Exception:
                pass

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    referrer_id INTEGER,
                    is_partner INTEGER DEFAULT 0,
                    partner_expires_at TIMESTAMP,
                    gift_markup_percent REAL,
                    stars_markup_percent REAL,
                    partner_balance INTEGER DEFAULT 0,
                    hold_until TIMESTAMP,
                    expiry_notified INTEGER DEFAULT 0,
                    is_blocked INTEGER DEFAULT 0,
                    blocked_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS vip_users (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS gift_stickers (
                    gift_id INTEGER PRIMARY KEY,
                    sticker_file_id TEXT
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS catalog (
                    gift_id INTEGER PRIMARY KEY,
                    title TEXT,
                    stars INTEGER,
                    sticker_file_id TEXT,
                    emoji_id TEXT,
                    is_active INTEGER DEFAULT 1
                );
            """)



            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    gift_id INTEGER,
                    gifts_data TEXT,
                    target_peer TEXT,
                    send_method TEXT,
                    is_anonymous INTEGER,
                    message TEXT,
                    base_stars INTEGER,
                    total_stars INTEGER,
                    fee_stars INTEGER,
                    charge_id TEXT,
                    status TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS stars_orders (
                    order_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    target_username TEXT,
                    stars_amount INTEGER,
                    ton_price REAL,
                    status TEXT,
                    memo TEXT,
                    payment_method TEXT DEFAULT 'TON',
                    crypto_amount REAL DEFAULT 0.0,
                    crypto_currency TEXT DEFAULT 'TON',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    channel_title TEXT,
                    channel_username TEXT,
                    is_private INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, channel_id)
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS referral_earnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    partner_id INTEGER NOT NULL,
                    referral_id INTEGER NOT NULL,
                    order_id TEXT,
                    order_type TEXT,
                    margin_stars INTEGER DEFAULT 0,
                    earned_stars INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount_stars INTEGER NOT NULL,
                    ton_address TEXT NOT NULL,
                    memo TEXT,
                    status TEXT DEFAULT 'pending',
                    admin_comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS partner_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT DEFAULT 'new',
                    status TEXT DEFAULT 'pending',
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS received_ton_transactions (
                    tx_hash TEXT PRIMARY KEY,
                    lt INTEGER NOT NULL,
                    currency TEXT DEFAULT 'TON',
                    amount REAL NOT NULL,
                    memo TEXT,
                    sender TEXT,
                    is_used INTEGER DEFAULT 0,
                    matched_order_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_ton_tx_memo ON received_ton_transactions(memo);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_ton_tx_lt ON received_ton_transactions(lt);")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)
            
            # Migrate existing tables if needed
            try:
                await db.execute("ALTER TABLE orders ADD COLUMN gifts_data TEXT")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE stars_orders ADD COLUMN payment_method TEXT DEFAULT 'TON'")
                await db.execute("ALTER TABLE stars_orders ADD COLUMN crypto_amount REAL DEFAULT 0.0")
                await db.execute("ALTER TABLE stars_orders ADD COLUMN crypto_currency TEXT DEFAULT 'TON'")
            except Exception:
                pass

            # Users table columns for Partner and Referral Program
            user_cols_to_add = [
                ("referrer_id", "INTEGER"),
                ("is_partner", "INTEGER DEFAULT 0"),
                ("partner_expires_at", "TIMESTAMP"),
                ("gift_markup_percent", "REAL"),
                ("stars_markup_percent", "REAL"),
                ("partner_balance", "INTEGER DEFAULT 0"),
                ("hold_until", "TIMESTAMP"),
                ("expiry_notified", "INTEGER DEFAULT 0"),
                ("invited_by_promo", "TEXT"),
                ("is_blocked", "INTEGER DEFAULT 0"),
                ("blocked_at", "TIMESTAMP")
            ]
            for col_name, col_type in user_cols_to_add:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

            # Ensure default settings exist
            await db.execute("""
                INSERT OR IGNORE INTO settings (key, value)
                VALUES ('markup_percent', ?)
            """, (str(DEFAULT_MARKUP_PERCENT),))
            
            await db.execute("""
                INSERT OR IGNORE INTO settings (key, value)
                VALUES ('stars_markup_percent', ?)
            """, (str(STARS_MARKUP_PERCENT),))

            await db.execute("""
                CREATE TABLE IF NOT EXISTS promo_links (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    gift_markup_percent REAL NOT NULL,
                    stars_markup_percent REAL NOT NULL,
                    duration_days INTEGER DEFAULT 30,
                    activations_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Ensure default promo link exists
            async with db.execute("SELECT COUNT(*) FROM promo_links") as cursor:
                count_row = await cursor.fetchone()
                if count_row and count_row[0] == 0:
                    legacy_code = "forum"
                    async with db.execute("SELECT value FROM settings WHERE key = 'promo_code'") as promo_cur:
                        promo_row = await promo_cur.fetchone()
                        if promo_row and promo_row[0]:
                            legacy_code = promo_row[0].strip().lower()
                    await db.execute("""
                        INSERT INTO promo_links (code, name, gift_markup_percent, stars_markup_percent, duration_days, activations_count, is_active)
                        VALUES (?, ?, ?, ?, ?, 0, 1)
                    """, (legacy_code, "Реклама на форуме", 15.0, 10.0, 30))

            # Ensure default catalog gifts are present and have correct is_active, emoji_ids and names
            for g in DEFAULT_CATALOG_GIFTS:
                await db.execute("""
                    INSERT INTO catalog (gift_id, title, stars, emoji_id, is_active)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(gift_id) DO UPDATE SET
                        emoji_id = COALESCE(excluded.emoji_id, catalog.emoji_id),
                        is_active = excluded.is_active,
                        stars = excluded.stars,
                        title = CASE WHEN catalog.title LIKE 'Gift #%' THEN excluded.title ELSE catalog.title END
                """, (g["gift_id"], g["title"], g["stars"], g.get("emoji_id"), g.get("is_active", 0)))

            await db.commit()

    async def sync_catalog_gifts(self, gifts: List[Dict[str, Any]]):
        async with aiosqlite.connect(self.db_path) as db:
            for g in gifts:
                is_active = g.get("is_active", 1)
                emoji_id = g.get("emoji_id")
                await db.execute("""
                    INSERT INTO catalog (gift_id, title, stars, sticker_file_id, emoji_id, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(gift_id) DO UPDATE SET
                        title = excluded.title,
                        stars = excluded.stars,
                        sticker_file_id = COALESCE(excluded.sticker_file_id, catalog.sticker_file_id),
                        emoji_id = COALESCE(excluded.emoji_id, catalog.emoji_id),
                        is_active = excluded.is_active
                """, (g["gift_id"], g["title"], g["stars"], g.get("sticker_file_id"), emoji_id, is_active))
            await db.commit()

    async def auto_match_emojis(self, cache_dir: str = "stickers_cache") -> int:
        import os, hashlib
        if not os.path.exists(cache_dir):
            return 0
            
        hashes = {}
        for f in os.listdir(cache_dir):
            if f.endswith('.tgs'):
                filepath = os.path.join(cache_dir, f)
                if os.path.getsize(filepath) > 0:
                    with open(filepath, 'rb') as file:
                        h = hashlib.md5(file.read()).hexdigest()
                        hashes.setdefault(h, []).append(f)
                        
        gift_to_emoji = {}
        for h, lst in hashes.items():
            g_id = None
            e_id = None
            for x in lst:
                if x.startswith('custom_'):
                    e_id = x[7:-4]
                else:
                    g_id = x[:-4]
            if g_id and e_id and g_id.isdigit():
                gift_to_emoji[int(g_id)] = e_id
                
        if not gift_to_emoji:
            return 0
            
        async with aiosqlite.connect(self.db_path) as db:
            for gid, eid in gift_to_emoji.items():
                await db.execute("UPDATE catalog SET emoji_id = ? WHERE gift_id = ?", (eid, gid))
            await db.commit()
            
        return len(gift_to_emoji)

    async def update_catalog_emoji(self, gift_id: int, emoji_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE catalog SET emoji_id = ? WHERE gift_id = ?", (emoji_id, gift_id))
            await db.commit()

    async def register_user(self, user_id: int, username: Optional[str], first_name: Optional[str]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO users (user_id, username, first_name, is_blocked)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    is_blocked = 0
            """, (user_id, username, first_name))
            await db.commit()

    async def mark_user_blocked(self, user_id: int):
        """Marks that the user has blocked the bot (e.g. detected during broadcast)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users 
                SET is_blocked = 1, blocked_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (user_id,))
            await db.commit()

    async def unmark_user_blocked(self, user_id: int):
        """Unmarks user blocked status when bot successfully interacts with them."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users 
                SET is_blocked = 0 
                WHERE user_id = ?
            """, (user_id,))
            await db.commit()

    async def get_blocked_users(self) -> List[Dict[str, Any]]:
        """Returns list of users who blocked the bot."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT user_id, username, first_name, blocked_at, created_at 
                FROM users 
                WHERE is_blocked = 1 
                ORDER BY blocked_at DESC, user_id ASC
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_blocked_users_count(self) -> int:
        """Returns total count of users who blocked the bot."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_users_list(
        self,
        page: int = 1,
        per_page: int = 10,
        search_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Returns paginated list of users with total count and VIP/partner statuses."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            where_clauses = []
            params: list = []
            if search_query:
                q = f"%{search_query.strip().lower()}%"
                if search_query.strip().isdigit():
                    where_clauses.append("(u.user_id = ? OR LOWER(u.username) LIKE ? OR LOWER(u.first_name) LIKE ?)")
                    params.extend([int(search_query.strip()), q, q])
                else:
                    where_clauses.append("(LOWER(u.username) LIKE ? OR LOWER(u.first_name) LIKE ?)")
                    params.extend([q, q])

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            count_query = f"SELECT COUNT(*) FROM users u {where_sql}"
            async with db.execute(count_query, params) as cursor:
                total_count = (await cursor.fetchone())[0]

            total_pages = max(1, (total_count + per_page - 1) // per_page)
            page = max(1, min(page, total_pages)) if total_count > 0 else 1
            offset = (page - 1) * per_page

            query = f"""
                SELECT 
                    u.*,
                    (SELECT COUNT(*) FROM users r WHERE r.referrer_id = u.user_id) as referrals_count,
                    (SELECT 1 FROM vip_users v WHERE v.user_id = u.user_id) as is_vip_user
                FROM users u
                {where_sql}
                ORDER BY u.created_at DESC, u.user_id DESC
                LIMIT ? OFFSET ?
            """
            async with db.execute(query, params + [per_page, offset]) as cursor:
                rows = await cursor.fetchall()
                users = [dict(r) for r in rows]

            return {
                "users": users,
                "total_count": total_count,
                "page": page,
                "total_pages": total_pages,
                "per_page": per_page
            }

    async def get_blocked_users_paged(
        self,
        page: int = 1,
        per_page: int = 10
    ) -> Dict[str, Any]:
        """Returns paginated list of users who blocked the bot."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1") as cursor:
                total_count = (await cursor.fetchone())[0]

            total_pages = max(1, (total_count + per_page - 1) // per_page)
            page = max(1, min(page, total_pages)) if total_count > 0 else 1
            offset = (page - 1) * per_page

            query = """
                SELECT user_id, username, first_name, blocked_at, created_at 
                FROM users 
                WHERE is_blocked = 1 
                ORDER BY blocked_at DESC, user_id ASC
                LIMIT ? OFFSET ?
            """
            async with db.execute(query, (per_page, offset)) as cursor:
                rows = await cursor.fetchall()
                users = [dict(r) for r in rows]

            return {
                "users": users,
                "total_count": total_count,
                "page": page,
                "total_pages": total_pages,
                "per_page": per_page
            }

    async def set_user_promo_source(self, user_id: int, promo_code: str):
        """Sets or updates the promo link code the user joined from."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET invited_by_promo = ? WHERE user_id = ?
            """, (promo_code.strip().lower(), user_id))
            await db.commit()

    async def get_all_user_ids(self) -> List[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def is_vip(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT 1 FROM vip_users WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone() is not None

    async def get_vip_users(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM vip_users ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def add_vip_user(self, user_id: int, added_by: Optional[int] = None, note: str = "") -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO vip_users (user_id, added_by, note)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET note = excluded.note
                """, (user_id, added_by, note))
                await db.commit()
                return True
            except Exception:
                return False

    async def remove_vip_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM vip_users WHERE user_id = ?", (user_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_markup_percent(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = 'markup_percent'") as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        return float(row[0])
                    except ValueError:
                        pass
        return DEFAULT_MARKUP_PERCENT

    async def set_markup_percent(self, value: float):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO settings (key, value)
                VALUES ('markup_percent', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (str(value),))
            await db.commit()

    async def get_stars_markup_percent(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = 'stars_markup_percent'") as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        return float(row[0])
                    except ValueError:
                        pass
        return STARS_MARKUP_PERCENT

    async def set_stars_markup_percent(self, value: float):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO settings (key, value)
                VALUES ('stars_markup_percent', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (str(value),))
            await db.commit()

    async def get_all_promo_links(self) -> List[Dict[str, Any]]:
        """Returns all promo links ordered by created_at."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM promo_links ORDER BY created_at ASC") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_promo_link(self, code: str) -> Optional[Dict[str, Any]]:
        """Finds a promo link by code (case-insensitive)."""
        if not code:
            return None
        code_clean = code.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM promo_links WHERE LOWER(code) = LOWER(?)", (code_clean,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def create_promo_link(
        self,
        code: str,
        name: str,
        gift_markup: float,
        stars_markup: float,
        duration_days: int = 30
    ) -> bool:
        """Creates a new promo link."""
        code_clean = code.strip().lower()
        if not code_clean:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO promo_links (code, name, gift_markup_percent, stars_markup_percent, duration_days, activations_count, is_active)
                    VALUES (?, ?, ?, ?, ?, 0, 1)
                """, (code_clean, name.strip(), float(gift_markup), float(stars_markup), int(duration_days)))
                await db.commit()
                return True
            except Exception:
                return False

    async def update_promo_link(
        self,
        code: str,
        gift_markup: Optional[float] = None,
        stars_markup: Optional[float] = None,
        duration_days: Optional[int] = None,
        is_active: Optional[int] = None,
        name: Optional[str] = None
    ) -> bool:
        """Updates promo link parameters."""
        code_clean = code.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            updates = []
            params = []
            if gift_markup is not None:
                updates.append("gift_markup_percent = ?")
                params.append(float(gift_markup))
            if stars_markup is not None:
                updates.append("stars_markup_percent = ?")
                params.append(float(stars_markup))
            if duration_days is not None:
                updates.append("duration_days = ?")
                params.append(int(duration_days))
            if is_active is not None:
                updates.append("is_active = ?")
                params.append(int(is_active))
            if name is not None:
                updates.append("name = ?")
                params.append(name.strip())

            if not updates:
                return False

            params.append(code_clean)
            query = f"UPDATE promo_links SET {', '.join(updates)} WHERE LOWER(code) = LOWER(?)"
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount > 0

    async def delete_promo_link(self, code: str) -> bool:
        """Deletes a promo link by code."""
        code_clean = code.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM promo_links WHERE LOWER(code) = LOWER(?)", (code_clean,))
            await db.commit()
            return cursor.rowcount > 0

    async def increment_promo_activations(self, code: str):
        """Increments the activation count of a promo link."""
        code_clean = code.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE promo_links SET activations_count = activations_count + 1
                WHERE LOWER(code) = LOWER(?)
            """, (code_clean,))
            await db.commit()

    async def get_promo_code(self) -> str:
        """Returns the configured custom promo tag for forum/ad links (default 'forum')."""
        links = await self.get_all_promo_links()
        if links:
            return links[0]["code"]
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = 'promo_code'") as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return row[0].strip()
        return "forum"

    async def set_promo_code(self, value: str):
        """Sets the custom promo tag."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO settings (key, value)
                VALUES ('promo_code', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (value.strip().lower(),))
            await db.commit()

    async def get_evm_fee(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = 'evm_fee'") as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        return float(row[0])
                    except ValueError:
                        pass
        return 0.10

    async def set_evm_fee(self, value: float):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO settings (key, value)
                VALUES ('evm_fee', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (str(value),))
            await db.commit()

    async def get_payment_methods_status(self) -> Dict[str, bool]:
        """Returns dict of payment methods and whether each is enabled (True) or disabled (False)."""
        methods = {
            "TON_NATIVE": True,
            "TON_USDT": True,
            "POL_USDT": True,
            "POL_USDC": True,
            "BASE_USDC": True,
        }
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT key, value FROM settings WHERE key LIKE 'paymethod_%'") as cursor:
                rows = await cursor.fetchall()
                for key, val in rows:
                    method_name = key.replace("paymethod_", "")
                    if method_name in methods:
                        methods[method_name] = (val == "1" or val.lower() == "true")
        return methods

    async def is_payment_method_enabled(self, method: str) -> bool:
        """Checks if a specific payment method is enabled."""
        status_map = await self.get_payment_methods_status()
        return status_map.get(method, True)

    async def set_payment_method_status(self, method: str, is_enabled: bool):
        """Sets the enabled status of a payment method."""
        key = f"paymethod_{method}"
        val = "1" if is_enabled else "0"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, val))
            await db.commit()

    async def toggle_payment_method(self, method: str) -> bool:
        """Toggles the enabled status of a payment method and returns new status."""
        current_status = await self.is_payment_method_enabled(method)
        new_status = not current_status
        await self.set_payment_method_status(method, new_status)
        return new_status

    async def set_gift_sticker(self, gift_id: int, sticker_file_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO gift_stickers (gift_id, sticker_file_id)
                VALUES (?, ?)
                ON CONFLICT(gift_id) DO UPDATE SET sticker_file_id = excluded.sticker_file_id
            """, (gift_id, sticker_file_id))
            await db.commit()

    async def get_gift_sticker(self, gift_id: int) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT sticker_file_id FROM gift_stickers WHERE gift_id = ?", (gift_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None


    async def get_catalog_gifts(self, active_only: bool = True) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM catalog" + (" WHERE is_active = 1" if active_only else "")
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                gifts = [dict(row) for row in rows]

            if not gifts:
                # Self-healing fallback: populate catalog immediately
                for g in DEFAULT_CATALOG_GIFTS:
                    await db.execute("""
                        INSERT INTO catalog (gift_id, title, stars, emoji_id, is_active)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(gift_id) DO UPDATE SET
                            emoji_id = COALESCE(excluded.emoji_id, catalog.emoji_id),
                            is_active = excluded.is_active,
                            stars = excluded.stars,
                            title = CASE WHEN catalog.title LIKE 'Gift #%' THEN excluded.title ELSE catalog.title END
                    """, (g["gift_id"], g["title"], g["stars"], g.get("emoji_id"), g.get("is_active", 0)))
                await db.commit()
                async with db.execute(query) as cursor:
                    rows = await cursor.fetchall()
                    gifts = [dict(row) for row in rows]

            # 11 hidden gifts must come first in exact user order, followed by active store gifts
            PRIORITY_IDS = [
                6046178578163303744, 5974210632977745012, 6026193266406327981, 5969796561943660080,
                5935895822435615975, 5893356958802511476, 5866352046986232958, 5800655655995968830,
                5801108895304779062, 5956217000635139069, 5922558454332916696
            ]
            p_map = {gid: idx for idx, gid in enumerate(PRIORITY_IDS)}
            gifts.sort(key=lambda g: (p_map.get(g["gift_id"], 999), g.get("stars", 0), g["gift_id"]))
            return gifts

    async def get_catalog_gift_by_id(self, gift_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM catalog WHERE gift_id = ?", (gift_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
            
            # Fallback to default gifts
            for g in DEFAULT_CATALOG_GIFTS:
                if g["gift_id"] == gift_id:
                    return dict(g)
            return None

    async def add_catalog_gift(self, gift_id: int, title: str, stars: int, sticker_file_id: Optional[str] = None) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO catalog (gift_id, title, stars, sticker_file_id, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(gift_id) DO UPDATE SET
                        title = excluded.title,
                        stars = excluded.stars,
                        sticker_file_id = COALESCE(excluded.sticker_file_id, catalog.sticker_file_id),
                        is_active = 1
                """, (gift_id, title, stars, sticker_file_id))
                await db.commit()
                return True
            except Exception:
                return False

    async def update_gift_sticker(self, gift_id: int, sticker_file_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE catalog SET sticker_file_id = ? WHERE gift_id = ?", (sticker_file_id, gift_id))
            await db.commit()

    async def remove_catalog_gift(self, gift_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM catalog WHERE gift_id = ?", (gift_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def create_order(self, order_data: Dict[str, Any]) -> bool:
        import json
        data_copy = dict(order_data)
        if "gifts_data" in data_copy and isinstance(data_copy["gifts_data"], (list, dict)):
            data_copy["gifts_data"] = json.dumps(data_copy["gifts_data"], ensure_ascii=False)
        elif "gifts_data" not in data_copy:
            data_copy["gifts_data"] = None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO orders (
                    order_id, user_id, gift_id, gifts_data, target_peer, send_method,
                    is_anonymous, message, base_stars, total_stars, fee_stars,
                    charge_id, status, error_message
                )
                VALUES (
                    :order_id, :user_id, :gift_id, :gifts_data, :target_peer, :send_method,
                    :is_anonymous, :message, :base_stars, :total_stars, :fee_stars,
                    :charge_id, :status, :error_message
                )
            """, data_copy)
            await db.commit()
            return True

    async def update_order_status(self, order_id: str, status: str, charge_id: Optional[str] = None, error_message: Optional[str] = None):
        async with aiosqlite.connect(self.db_path) as db:
            updates = ["status = ?"]
            params = [status]
            if charge_id:
                updates.append("charge_id = ?")
                params.append(charge_id)
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            params.append(order_id)
            query = f"UPDATE orders SET {', '.join(updates)} WHERE order_id = ?"
            await db.execute(query, params)
            await db.commit()

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        import json
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                order = dict(row)
                
                # Parse gifts_data
                gifts = []
                if order.get("gifts_data"):
                    try:
                        gifts = json.loads(order["gifts_data"])
                    except Exception:
                        pass
                
                # Fallback to single gift_id
                if not gifts and order.get("gift_id"):
                    gifts = [{"gift_id": order["gift_id"], "stars": order.get("base_stars", 50)}]
                
                order["gifts"] = gifts
                return order

    async def create_stars_order(self, order_data: Dict[str, Any]) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            # Provide defaults for the new fields if they are missing
            payment_method = order_data.get('payment_method', 'TON')
            crypto_amount = order_data.get('crypto_amount', order_data.get('ton_price', 0.0))
            crypto_currency = order_data.get('crypto_currency', 'TON')
            
            await db.execute("""
                INSERT INTO stars_orders (
                    order_id, user_id, target_username, stars_amount,
                    ton_price, status, memo, payment_method, crypto_amount, crypto_currency
                )
                VALUES (
                    :order_id, :user_id, :target_username, :stars_amount,
                    :ton_price, :status, :memo, :payment_method, :crypto_amount, :crypto_currency
                )
            """, {
                **order_data,
                "payment_method": payment_method,
                "crypto_amount": crypto_amount,
                "crypto_currency": crypto_currency
            })
            await db.commit()
            return True

    async def update_stars_order_status(self, order_id: str, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE stars_orders SET status = ? WHERE order_id = ?", (status, order_id))
            await db.commit()

    async def try_mark_stars_order_processing(self, order_id: str) -> bool:
        """Atomically transitions order from pending to processing. Returns True if successfully acquired."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE stars_orders
                SET status = 'processing'
                WHERE order_id = ? AND status = 'pending'
            """, (order_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_stars_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM stars_orders WHERE order_id = ?", (order_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_stats(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                users_count = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1") as cursor:
                blocked_count = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM vip_users") as cursor:
                vip_count = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'") as cursor:
                completed_orders = (await cursor.fetchone())[0]
            async with db.execute("SELECT COALESCE(SUM(fee_stars), 0) FROM orders WHERE status = 'completed'") as cursor:
                total_earned_stars = (await cursor.fetchone())[0]
            async with db.execute("SELECT COALESCE(SUM(stars_amount), 0) FROM stars_orders WHERE status = 'completed'") as cursor:
                sold_stars = (await cursor.fetchone())[0]
            return {
                "users_count": users_count,
                "blocked_count": blocked_count,
                "vip_count": vip_count,
                "completed_orders": completed_orders,
                "total_earned_stars": total_earned_stars,
                "sold_stars": sold_stars
            }

    async def get_gift_sticker(self, gift_id: int) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT sticker_file_id FROM gift_stickers WHERE gift_id = ?", (gift_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] else None

    async def set_gift_sticker(self, gift_id: int, file_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO gift_stickers (gift_id, sticker_file_id)
                VALUES (?, ?)
                ON CONFLICT(gift_id) DO UPDATE SET sticker_file_id = excluded.sticker_file_id
            """, (gift_id, file_id))
            await db.commit()

    async def get_all_cached_stickers(self) -> Dict[int, str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT gift_id, sticker_file_id FROM gift_stickers WHERE sticker_file_id IS NOT NULL") as cursor:
                rows = await cursor.fetchall()
                return {
                    r[0]: r[1] for r in rows
                    if r[1] and not r[1].endswith(".tgs") and "\\" not in r[1] and "/" not in r[1]
                }

    async def add_user_channel(
        self,
        user_id: int,
        channel_id: int,
        channel_title: str,
        channel_username: Optional[str] = None,
        is_private: bool = True
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO user_channels (user_id, channel_id, channel_title, channel_username, is_private, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id, channel_id) DO UPDATE SET
                    channel_title = excluded.channel_title,
                    channel_username = excluded.channel_username,
                    is_private = excluded.is_private,
                    is_active = 1
            """, (user_id, channel_id, channel_title, channel_username, 1 if is_private else 0))
            await db.commit()

    async def deactivate_user_channel(self, channel_id: int, user_id: Optional[int] = None):
        async with aiosqlite.connect(self.db_path) as db:
            if user_id is not None:
                await db.execute(
                    "UPDATE user_channels SET is_active = 0 WHERE channel_id = ? AND user_id = ?",
                    (channel_id, user_id)
                )
            else:
                await db.execute(
                    "UPDATE user_channels SET is_active = 0 WHERE channel_id = ?",
                    (channel_id,)
                )
            await db.commit()

    async def get_user_channels(self, user_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM user_channels WHERE user_id = ? AND is_active = 1 ORDER BY added_at DESC",
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_user_channel_by_id(self, user_id: int, channel_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM user_channels WHERE user_id = ? AND channel_id = ? AND is_active = 1",
                (user_id, channel_id)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None


    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_user_gift_markup(self, user_id: int) -> float:
        """Returns the gift markup percent for a user (partner discount if active, otherwise default)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT is_partner, partner_expires_at, gift_markup_percent FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row["is_partner"]:
                    expires = row["partner_expires_at"]
                    # Check if not expired
                    is_active = True
                    if expires:
                        try:
                            exp_dt = datetime.datetime.fromisoformat(str(expires).replace("Z", ""))
                            if exp_dt < datetime.datetime.now():
                                is_active = False
                        except Exception:
                            pass
                    if is_active and row["gift_markup_percent"] is not None:
                        return float(row["gift_markup_percent"])
        return await self.get_markup_percent()

    async def get_user_stars_markup(self, user_id: int) -> float:
        """Returns the stars markup percent for a user (partner discount if active, otherwise default)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT is_partner, partner_expires_at, stars_markup_percent FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row["is_partner"]:
                    expires = row["partner_expires_at"]
                    # Check if not expired
                    is_active = True
                    if expires:
                        try:
                            exp_dt = datetime.datetime.fromisoformat(str(expires).replace("Z", ""))
                            if exp_dt < datetime.datetime.now():
                                is_active = False
                        except Exception:
                            pass
                    if is_active and row["stars_markup_percent"] is not None:
                        return float(row["stars_markup_percent"])
        return await self.get_stars_markup_percent()

    async def is_active_partner(self, user_id: int) -> bool:
        """Checks if user is an active partner whose program has not expired."""
        user = await self.get_user(user_id)
        if not user or not user.get("is_partner"):
            return False
        expires = user.get("partner_expires_at")
        if expires:
            try:
                exp_dt = datetime.datetime.fromisoformat(str(expires).replace("Z", ""))
                if exp_dt < datetime.datetime.now():
                    return False
            except Exception:
                pass
        return True

    async def activate_partner(
        self,
        user_id: int,
        days: int = 30,
        gift_markup: float = 15.0,
        stars_markup: float = 10.0
    ) -> datetime.datetime:
        """Activates or renews partner status for specified days."""
        expires_at = datetime.datetime.now() + datetime.timedelta(days=days)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET
                    is_partner = 1,
                    partner_expires_at = ?,
                    gift_markup_percent = ?,
                    stars_markup_percent = ?,
                    expiry_notified = 0
                WHERE user_id = ?
            """, (expires_at.isoformat(), gift_markup, stars_markup, user_id))
            await db.commit()
        return expires_at

    async def update_partner_settings(
        self,
        user_id: int,
        gift_markup: Optional[float] = None,
        stars_markup: Optional[float] = None,
        partner_expires_at: Optional[datetime.datetime] = None,
        is_partner: Optional[int] = None
    ):
        async with aiosqlite.connect(self.db_path) as db:
            updates = []
            params = []
            if gift_markup is not None:
                updates.append("gift_markup_percent = ?")
                params.append(gift_markup)
            if stars_markup is not None:
                updates.append("stars_markup_percent = ?")
                params.append(stars_markup)
            if partner_expires_at is not None:
                updates.append("partner_expires_at = ?")
                updates.append("expiry_notified = 0")
                params.append(partner_expires_at.isoformat())
            if is_partner is not None:
                updates.append("is_partner = ?")
                params.append(is_partner)

            if updates:
                params.append(user_id)
                query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
                await db.execute(query, params)
                await db.commit()

    async def add_referral_if_none(self, user_id: int, referrer_id: int) -> bool:
        """Binds user to referrer if user does not have a referrer yet and user_id != referrer_id."""
        if user_id == referrer_id:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row and (row[0] is None or row[0] == 0):
                    await db.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
                    await db.commit()
                    return True
        return False

    async def add_partner_reward(
        self,
        partner_id: int,
        referral_id: int,
        order_id: str,
        order_type: str,
        margin_stars: int,
        earned_stars: int
    ) -> int:
        """Credits referral earnings to partner and initiates 21-day hold if balance reaches 1000."""
        async with aiosqlite.connect(self.db_path) as db:
            # 1. Record earnings
            await db.execute("""
                INSERT INTO referral_earnings (partner_id, referral_id, order_id, order_type, margin_stars, earned_stars)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (partner_id, referral_id, order_id, order_type, margin_stars, earned_stars))

            # 2. Update balance
            await db.execute("""
                UPDATE users SET partner_balance = COALESCE(partner_balance, 0) + ?
                WHERE user_id = ?
            """, (earned_stars, partner_id))

            # 3. Check balance and set hold_until if >= 1000 and hold_until is NULL
            async with db.execute("SELECT partner_balance, hold_until FROM users WHERE user_id = ?", (partner_id,)) as cursor:
                row = await cursor.fetchone()
                new_balance = row[0] if row else 0
                hold_until = row[1] if row else None

                if new_balance >= 1000 and (not hold_until or hold_until == ""):
                    hold_date = datetime.datetime.now() + datetime.timedelta(days=21)
                    await db.execute(
                        "UPDATE users SET hold_until = ? WHERE user_id = ?",
                        (hold_date.isoformat(), partner_id)
                    )

            await db.commit()
            return new_balance

    async def get_partner_stats(self, partner_id: int) -> Dict[str, Any]:
        """Calculates partner statistics including total referrals and referrals with >= 5 purchases."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # User profile info
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (partner_id,)) as cursor:
                user_row = await cursor.fetchone()
                user_dict = dict(user_row) if user_row else {}

            # All referrals
            query_refs = """
                SELECT u.user_id, u.username, u.first_name, u.created_at,
                       (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.user_id AND o.status = 'completed') +
                       (SELECT COUNT(*) FROM stars_orders so WHERE so.user_id = u.user_id AND so.status = 'completed') as total_orders
                FROM users u
                WHERE u.referrer_id = ?
            """
            async with db.execute(query_refs, (partner_id,)) as cursor:
                ref_rows = await cursor.fetchall()
                referrals = [dict(r) for r in ref_rows]

            total_referrals = len(referrals)
            active_referrals_5plus = sum(1 for r in referrals if r.get("total_orders", 0) >= 5)

            # Total earned
            async with db.execute(
                "SELECT COALESCE(SUM(earned_stars), 0) FROM referral_earnings WHERE partner_id = ?",
                (partner_id,)
            ) as cursor:
                total_earned_row = await cursor.fetchone()
                total_earned_stars = total_earned_row[0] if total_earned_row else 0

            # Expiration calculation
            partner_expires_at = user_dict.get("partner_expires_at")
            is_expired = False
            time_left_str = "Бессрочно"
            if partner_expires_at:
                try:
                    exp_dt = datetime.datetime.fromisoformat(str(partner_expires_at).replace("Z", ""))
                    now = datetime.datetime.now()
                    if exp_dt < now:
                        is_expired = True
                        time_left_str = "Истекла"
                    else:
                        diff = exp_dt - now
                        days = diff.days
                        hours = diff.seconds // 3600
                        time_left_str = f"{days} дн. {hours} ч."
                except Exception:
                    pass

            # Hold calculation
            hold_until = user_dict.get("hold_until")
            hold_active = False
            hold_left_str = "Нет холда"
            if hold_until:
                try:
                    h_dt = datetime.datetime.fromisoformat(str(hold_until).replace("Z", ""))
                    now = datetime.datetime.now()
                    if h_dt > now:
                        hold_active = True
                        diff = h_dt - now
                        days = diff.days
                        hours = diff.seconds // 3600
                        hold_left_str = f"{days} дн. {hours} ч. (до {h_dt.strftime('%d.%m.%Y %H:%M')})"
                    else:
                        hold_left_str = "Холд завершен"
                except Exception:
                    pass

            return {
                "user_id": partner_id,
                "username": user_dict.get("username"),
                "first_name": user_dict.get("first_name"),
                "is_partner": bool(user_dict.get("is_partner")),
                "is_expired": is_expired,
                "partner_expires_at": partner_expires_at,
                "time_left_str": time_left_str,
                "gift_markup_percent": user_dict.get("gift_markup_percent") or DEFAULT_MARKUP_PERCENT,
                "stars_markup_percent": user_dict.get("stars_markup_percent") or STARS_MARKUP_PERCENT,
                "partner_balance": user_dict.get("partner_balance", 0) or 0,
                "hold_until": hold_until,
                "hold_active": hold_active,
                "hold_left_str": hold_left_str,
                "total_referrals": total_referrals,
                "active_referrals_5plus": active_referrals_5plus,
                "total_earned_stars": total_earned_stars,
                "referrals": referrals,
                "invited_by_promo": user_dict.get("invited_by_promo"),
                "referrer_id": user_dict.get("referrer_id")
            }

    async def get_all_partners(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """Returns all partners with their stats for admin panel."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT DISTINCT u.user_id FROM users u
                WHERE u.is_partner = 1 OR u.partner_balance > 0 OR EXISTS(SELECT 1 FROM users r WHERE r.referrer_id = u.user_id)
                ORDER BY u.partner_expires_at DESC
            """
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                partner_ids = [r[0] for r in rows]

        partners = []
        for pid in partner_ids:
            stats = await self.get_partner_stats(pid)
            if active_only and (not stats["is_partner"] or stats["is_expired"]):
                continue
            partners.append(stats)
        return partners

    async def create_withdrawal_request(
        self,
        user_id: int,
        amount_stars: int,
        ton_address: str,
        memo: Optional[str] = None
    ) -> int:
        """Deducts balance and creates withdrawal request."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE users SET partner_balance = partner_balance - ?
                WHERE user_id = ?
            """, (amount_stars, user_id))

            cursor = await db.execute("""
                INSERT INTO withdrawal_requests (user_id, amount_stars, ton_address, memo, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (user_id, amount_stars, ton_address, memo))
            await db.commit()
            return cursor.lastrowid

    async def get_withdrawal_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM withdrawal_requests WHERE id = ?", (request_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_pending_withdrawals(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM withdrawal_requests WHERE status = 'pending' ORDER BY created_at ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def update_withdrawal_status(
        self,
        request_id: int,
        status: str,
        admin_comment: Optional[str] = None
    ) -> bool:
        """Updates withdrawal status. If rejected, refunds stars to partner balance."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM withdrawal_requests WHERE id = ?", (request_id,)) as cursor:
                req = await cursor.fetchone()
                if not req:
                    return False

            if status == "rejected" and req["status"] == "pending":
                # Refund balance
                await db.execute("""
                    UPDATE users SET partner_balance = partner_balance + ?
                    WHERE user_id = ?
                """, (req["amount_stars"], req["user_id"]))

            await db.execute("""
                UPDATE withdrawal_requests SET
                    status = ?,
                    admin_comment = ?,
                    processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, admin_comment, request_id))
            await db.commit()
            return True

    async def create_partner_application(self, user_id: int, app_type: str = "new", note: str = "") -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO partner_applications (user_id, type, status, note)
                VALUES (?, ?, 'pending', ?)
            """, (user_id, app_type, note))
            await db.commit()
            return cursor.lastrowid

    async def get_pending_applications(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM partner_applications WHERE status = 'pending' ORDER BY created_at ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_application_by_id(self, app_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM partner_applications WHERE id = ?", (app_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_application_status(self, app_id: int, status: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE partner_applications SET
                    status = ?,
                    processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, app_id))
            await db.commit()
            return cursor.rowcount > 0

    async def get_expired_unnotified_partners(self) -> List[Dict[str, Any]]:
        """Returns partners whose partner_expires_at is in the past and expiry_notified = 0."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM users
                WHERE is_partner = 1
                  AND partner_expires_at IS NOT NULL
                  AND partner_expires_at <= CURRENT_TIMESTAMP
                  AND (expiry_notified = 0 OR expiry_notified IS NULL)
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def mark_partner_expiry_notified(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET expiry_notified = 1 WHERE user_id = ?", (user_id,))
            await db.commit()

    # --- Settings ---
    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return row["value"] if row else default

    async def set_setting(self, key: str, value: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO bot_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, value))
            await db.commit()

    # --- TON Transactions Indexer & Claimer ---
    async def get_last_scanned_ton_lt(self) -> int:
        val = await self.get_setting("last_scanned_ton_lt", "0")
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    async def set_last_scanned_ton_lt(self, lt: int):
        await self.set_setting("last_scanned_ton_lt", str(lt))

    async def save_received_ton_tx(self, tx_data: Dict[str, Any]) -> bool:
        """
        Inserts a new incoming TON/Jetton transaction into the local cache.
        Ignores duplicates based on tx_hash PRIMARY KEY.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT OR IGNORE INTO received_ton_transactions (
                    tx_hash, lt, currency, amount, memo, sender
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                tx_data["tx_hash"],
                tx_data["lt"],
                tx_data.get("currency", "TON"),
                tx_data["amount"],
                tx_data.get("memo"),
                tx_data.get("sender")
            ))
            await db.commit()
            return cursor.rowcount > 0

    async def claim_received_ton_tx(
        self,
        memo: str,
        expected_amount: float,
        order_id: str,
        currency: str = "TON"
    ) -> bool:
        """
        Atomically finds an unspent transaction for the given memo and amount,
        marks it is_used = 1, and links it to order_id.
        Prevents double-spend and collisions across concurrent requests.
        """
        if not memo:
            return False
        clean_memo = memo.strip()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Check for available transaction
            async with db.execute("""
                SELECT tx_hash, amount FROM received_ton_transactions
                WHERE memo = ? AND currency = ? AND is_used = 0 AND amount >= ?
                ORDER BY lt ASC LIMIT 1
            """, (clean_memo, currency, expected_amount)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return False
                tx_hash = row["tx_hash"]

            # Atomic claim
            cursor = await db.execute("""
                UPDATE received_ton_transactions
                SET is_used = 1, matched_order_id = ?
                WHERE tx_hash = ? AND is_used = 0
            """, (order_id, tx_hash))
            await db.commit()
            return cursor.rowcount > 0


_db_instance: Optional[Database] = None

def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

