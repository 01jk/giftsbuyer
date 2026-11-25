import json
import logging
from typing import Optional, Dict, Any, Tuple
from config import FRAGMENT_COOKIES, FRAGMENT_SEED, TONCONSOLE_API_KEY, STARS_MARKUP_PERCENT
from FragmentAPI import FragmentClient

logger = logging.getLogger(__name__)

class FragmentService:
    def __init__(self):
        try:
            raw_cookies = json.loads(FRAGMENT_COOKIES)
            if isinstance(raw_cookies, list):
                # Convert from browser extension format
                self.cookies = {c["name"]: c["value"] for c in raw_cookies if "name" in c and "value" in c}
            else:
                self.cookies = raw_cookies
        except Exception:
            self.cookies = {}
        
        self.seed = FRAGMENT_SEED.strip() if FRAGMENT_SEED else None
        self.api_key = TONCONSOLE_API_KEY.strip() if TONCONSOLE_API_KEY else None
        
        # We need stel_ton_token and seed for purchasing
        self.can_purchase = bool(self.cookies.get("stel_ton_token") and self.seed and self.api_key)

    async def get_stars_price_ton(self, amount: int, user_id: int) -> Optional[float]:
        """
        Fetches the cost of stars on Fragment and applies markup.
        Returns the final price in TON, or None if error.
        """
        try:
            async with FragmentClient(cookies=self.cookies) as client:
                prices = await client.get_stars_prices()
                # Find the package matching the amount or calculate proportionally if not exact match
                
                exact_pkg = next((p for p in prices.packages if p.stars == amount), None)
                if exact_pkg:
                    base_price = float(exact_pkg.gram_price)
                else:
                    price_info = await client.get_stars_price(amount)
                    base_price = float(price_info.gram_price)

                if base_price is None:
                    return None
                
                from database.db import get_db
                db = get_db()
                if await db.is_vip(user_id):
                    markup_percent = 0.0
                else:
                    markup_percent = await db.get_user_stars_markup(user_id)

                markup_multiplier = 1.0 + (markup_percent / 100.0)
                final_price = base_price * markup_multiplier
                return round(final_price, 3)
                
        except Exception as e:
            logger.error(f"Error fetching stars price from Fragment: {e}")
            return None

    async def purchase_stars(self, target_username: str, amount: int, payment_method: str = "gram") -> Tuple[bool, str, Any]:
        """
        Purchases stars for the given username.
        Returns (success, transaction_id_or_error_message, invoice_data).
        invoice_data is used for EVM payments.
        """
        if not self.can_purchase:
            return False, "Fragment Service is not fully configured (missing cookies, seed, or api key).", None

        try:
            client_cookies = dict(self.cookies)
            
            async with FragmentClient(
                cookies=client_cookies,
                seed=self.seed,
                api_key=self.api_key,
                wallet_version="V4R2"
            ) as client:
                result = await client.purchase_stars(
                    username=target_username,
                    amount=amount,
                    show_sender=False,
                    payment_method=payment_method
                )
                
                if hasattr(result, "invoice") and result.invoice:
                    # EVM purchase result (if FragmentAPI ever fixes it)
                    return True, "EVM_INVOICE", {
                        "address": result.invoice.invoice_address,
                        "amount": float(result.invoice.invoice_amount)
                    }
                elif hasattr(result, "transaction_id"):
                    return True, result.transaction_id, None
                else:
                    return False, "Failed to get transaction ID.", None
        except Exception as e:
            if "EVM payment may not be supported" in str(e) or "Invoice data missing" in str(e):
                logger.info(f"FragmentAPI failed for EVM, falling back to optimized Playwright flow...")
                return await self._purchase_evm_playwright(target_username, amount, payment_method)
            logger.error(f"Error purchasing stars on Fragment: {e}")
            return False, str(e), None

    async def _purchase_evm_playwright(self, target_username: str, amount: int, payment_method: str) -> Tuple[bool, str, Any]:
        """Custom API using fast headless Playwright to fetch the EVM invoice."""
        from playwright.async_api import async_playwright
        import re
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            
            # Inject session cookies
            pw_cookies = []
            for k, v in self.cookies.items():
                pw_cookies.append({"name": k, "value": str(v), "domain": ".fragment.com", "path": "/"})
            if pw_cookies:
                await context.add_cookies(pw_cookies)
                
            page = await context.new_page()
            
            # Block images and media for speed, but allow CSS
            await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())
            
            try:
                # 1. Resolve username to recipient ID using FragmentAPI
                from FragmentAPI import FragmentClient
                recipient_id = target_username
                if not target_username.startswith("F-"): # Not a self-recipient ID
                    try:
                        async with FragmentClient(cookies=self.cookies) as f_client:
                            rec_info = await f_client.get_stars_recipient(target_username)
                            if rec_info and rec_info.recipient:
                                recipient_id = rec_info.recipient
                    except Exception as e:
                        logger.warning(f"Could not resolve username via FragmentAPI, using raw username: {e}")
                
                # 2. Navigate directly to the pre-filled URL to save time.
                url = f"https://fragment.com/stars/buy?recipient={recipient_id}&quantity={amount}"
                await page.goto(url, wait_until="domcontentloaded")
                
                # Check if it loaded correctly
                await page.wait_for_selector('.js-stars-buy-btn')
                
                # Map payment method
                pm_map = {
                    "usdt_eth": "USDT ETH", "usdt_pol": "USDT POL", "usdt_ton": "USDT TON",
                    "usdc_eth": "USDC ETH", "usdc_base": "USDC Base", "usdc_pol": "USDC POL"
                }
                pm_text = pm_map.get(payment_method.lower())
                if not pm_text:
                    return False, f"Unsupported payment method for fallback: {payment_method}", None
                    
                # Open dropdowns based on base currency
                if "USDT" in pm_text:
                    await page.evaluate("Array.from(document.querySelectorAll('.tm-currency-tab')).find(el => el.textContent.includes('USDT')).click()")
                else:
                    await page.evaluate("Array.from(document.querySelectorAll('.tm-currency-tab')).find(el => el.textContent.includes('USDC')).click()")
                
                await page.wait_for_timeout(1000)
                
                # Click specific network (using Playwright locator for robust text matching)
                currency_item = page.locator('.js-currency-item', has_text=pm_text)
                await currency_item.click(force=True)
                
                await page.wait_for_timeout(1000)
                
                # Click buy button
                await page.locator('.js-stars-buy-btn').click(force=True)
                
                # Wait for popup
                await page.wait_for_selector('.js-buy-stars-form button[type="submit"]')
                await page.wait_for_timeout(1000)
                
                # Make it anonymous (uncheck "Show my name to the recipient")
                try:
                    await page.evaluate("document.querySelector('input[name=\"show_sender\"]').checked = false;")
                except Exception as e:
                    logger.warning(f"Failed to uncheck show_sender: {e}")
                
                # Click confirm
                await page.locator('.js-buy-stars-form button[type="submit"]').click(force=True)
                
                # Now wait for the invoice to render! It should show a QR code or an address
                # Wait until the page contains an Ethereum-style address
                address = None
                for _ in range(15):
                    await page.wait_for_timeout(1000)
                    content = await page.content()
                    match = re.search(r"0x[a-fA-F0-9]{40}", content)
                    if match:
                        address = match.group(0)
                        break
                        
                if not address:
                    await page.screenshot(path="scratch/fail.png")
                    return False, "Failed to get EVM invoice address from page. Saved screenshot to scratch/fail.png", None
                    
                # Find the exact amount
                # It is usually displayed as "0.75 USDC" inside the popup or invoice screen
                amount_val = 0.0
                try:
                    # Look for something like "0.75 USDC" anywhere in the body text
                    amount_text = await page.evaluate("document.body.innerText")
                    amount_match = re.search(r"(\d+\.\d{1,6})\s*(USDC|USDT|ETH|POL|Base|TON)", amount_text, re.IGNORECASE)
                    if amount_match:
                        amount_val = float(amount_match.group(1))
                except Exception:
                    pass
                    
                return True, "EVM_INVOICE", {"address": address, "amount": amount_val}
                
            except Exception as e:
                logger.error(f"Playwright EVM fallback error: {e}")
                return False, f"Playwright EVM fallback error: {e}", None
            finally:
                await browser.close()



    async def get_wallet_address(self) -> Optional[str]:
        """
        Returns the TON address of the connected Fragment wallet.
        """
        if not self.can_purchase:
            return None
            
        try:
            async with FragmentClient(
                cookies=self.cookies,
                seed=self.seed,
                api_key=self.api_key,
                wallet_version="V4R2"
            ) as client:
                wallet = await client.get_wallet()
                return wallet.address
        except Exception as e:
            logger.error(f"Error getting wallet address from Fragment: {e}")
            return None

fragment_service = FragmentService()
