# giftsbuyer

Telegram-бот для продажи и отправки подарков через магазин. Покупатель выбирает получателя и оплачивает заказ звёздами. Публичная версия поддерживает отправку от магазина.

Из корня проекта установите зависимости командой `python -m pip install -r requirements.txt` и скопируйте [.env.example](.env.example) в `.env`. В PowerShell для этого подойдёт `Copy-Item .env.example .env`.

Заполните `BOT_TOKEN` и укажите числовые Telegram ID администраторов в `ADMIN_IDS` через запятую. Для функций Telethon заполните `API_ID` и `API_HASH`. Владелец магазина создаёт собственную локальную сессию командой `python login_master.py`.

Запустите `python bot.py`. При первом запуске бот создаёт SQLite по пути `DB_PATH` и заполняет таблицу каталога из [default_catalog.py](database/default_catalog.py). В шаблоне задан локальный путь `data/gifts_buyer.db`. Для контейнера с томом, подключённым в `/data`, укажите `DB_PATH=/data/gifts_buyer.db`.
