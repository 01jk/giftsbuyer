import asyncio
from telethon import TelegramClient
from config import API_ID, API_HASH, BOT_MASTER_SESSION

async def main():
    print("=" * 50)
    print("Авторизация мастер-сессии бота (для отправки подарков «От бота»)")
    print("=" * 50)
    
    session_name = BOT_MASTER_SESSION.replace(".session", "")
    client = TelegramClient(session_name, API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        phone = input("Введите номер телефона (например +79991234567): ").strip()
        await client.send_code_request(phone)
        code = input("Введите код из Telegram/SMS: ").strip()
        try:
            await client.sign_in(phone, code)
        except Exception:
            password = input("Введите облачный пароль (2FA): ").strip()
            await client.sign_in(password=password)
    
    me = await client.get_me()
    print("\n" + "=" * 50)
    print(f"[+] УСПЕШНО АВТОРИЗОВАНО!")
    print(f"Аккаунт: {me.first_name} (@{me.username or 'нет юзернейма'}) [ID: {me.id}]")
    print(f"Сессия сохранена в файл: {BOT_MASTER_SESSION}")
    print("=" * 50)
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
