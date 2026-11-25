import asyncio
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.payments import GetPaymentFormRequest
from telethon.tl.types import InputInvoiceStarGift

from config import API_ID, API_HASH

GIFT_ID = 5801108895304779062   # ID подарка для проверки
TARGET_USER = "me"

async def main():
    print(" Инициализация клиента Telethon...")
    client = TelegramClient("session_gift_test", API_ID, API_HASH)
    
    # start() подключит клиент и запросит телефон/код, если вы еще не авторизованы
    await client.start()
    print(" Авторизация успешна! Подключение к Telegram...")

    try:
        peer = await client.get_input_entity(TARGET_USER)
        print(f" Получатель найден: {peer}")

        invoice = InputInvoiceStarGift(
            peer=peer,
            gift_id=GIFT_ID,
            hide_name=False
        )

        print("[4] Отправка запроса на получение формы оплаты (без списания звёзд)...")
        form = await client(GetPaymentFormRequest(invoice=invoice))
        print(f"[+] УСПЕХ: Подарок доступен для покупки! Form ID: {form.form_id}")

    except RPCError as e:
        print(f"[-] Ошибка Telegram API (подарок недоступен): {e.__class__.__name__} -> {e}")
    except Exception as e:
        print(f"[-] Другая ошибка: {type(e).__name__} -> {e}")
    finally:
        await client.disconnect()
        print("[5] Завершено.")

if __name__ == "__main__":
    asyncio.run(main())