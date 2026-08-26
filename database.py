import asyncio
import aiosqlite
import logging
from config import DB_PATH, DEFAULT_MANAGER

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()

async def get_db() -> aiosqlite.Connection:
    """One shared connection for the whole bot.

    Opening a fresh connection per query meant a file open plus PRAGMA setup on
    every button press; a single connection keeps the page cache warm and makes
    `synchronous=NORMAL` actually stick (it is per-connection, not per-file).
    """
    global _db
    if _db is None:
        async with _db_lock:
            if _db is None:
                conn = await aiosqlite.connect(DB_PATH)
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
                await conn.execute("PRAGMA busy_timeout=5000;")
                await conn.commit()
                _db = conn
    return _db

async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None

async def _add_column_if_missing(db, table: str, column: str, definition: str):
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    if column not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        logger.info(f"Migrated {table}: added {column}")

async def init_db():
    db = await get_db()

    await db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance REAL DEFAULT 0.0,
        ref_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        emoji TEXT DEFAULT '📁',
        parent_id INTEGER DEFAULT NULL,
        FOREIGN KEY (parent_id) REFERENCES categories (id)
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        stock INTEGER DEFAULT 50,
        badge TEXT DEFAULT '',
        is_available INTEGER DEFAULT 1,
        FOREIGN KEY (category_id) REFERENCES categories (id)
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS cart (
        user_id INTEGER,
        product_id INTEGER,
        quantity INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (user_id, product_id),
        FOREIGN KEY (product_id) REFERENCES products (id)
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_id INTEGER,
        quantity INTEGER NOT NULL DEFAULT 1,
        status TEXT DEFAULT 'В обработке',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Databases created before quantities existed need the column added.
    await _add_column_if_missing(db, "cart", "quantity", "INTEGER NOT NULL DEFAULT 1")
    await _add_column_if_missing(db, "orders", "quantity", "INTEGER NOT NULL DEFAULT 1")

    await db.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Add Performance Indexes
    await db.execute("CREATE INDEX IF NOT EXISTS idx_cat_parent ON categories (parent_id);")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_prod_cat ON products (category_id, is_available);")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_users_ref ON users (ref_id);")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders (user_id);")

    await db.commit()

    # Seed default settings if missing
    async with db.execute("SELECT value FROM settings WHERE key = 'manager_username'") as cursor:
        row = await cursor.fetchone()
        if not row:
            await db.execute("INSERT INTO settings (key, value) VALUES ('manager_username', ?)", (DEFAULT_MANAGER,))
            await db.commit()

    async with db.execute("SELECT value FROM settings WHERE key = 'payment_label'") as cursor:
        row = await cursor.fetchone()
        if not row:
            # Migrate the old single-field value if it exists, so nothing is lost
            async with db.execute("SELECT value FROM settings WHERE key = 'payment_requisites'") as old_cursor:
                old_row = await old_cursor.fetchone()
            label_default = old_row[0] if old_row else "Актуальные реквизиты уточняйте у менеджера."
            await db.execute("INSERT INTO settings (key, value) VALUES ('payment_label', ?)", (label_default,))
            await db.commit()

    async with db.execute("SELECT value FROM settings WHERE key = 'payment_address'") as cursor:
        row = await cursor.fetchone()
        if not row:
            await db.execute("INSERT INTO settings (key, value) VALUES ('payment_address', ?)", ("",))
            await db.commit()

    # Bump order numbering so new orders start from #7535 onward
    order_number_floor = 7534
    async with db.execute("SELECT seq FROM sqlite_sequence WHERE name = 'orders'") as cursor:
        row = await cursor.fetchone()
    if row is None:
        await db.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('orders', ?)", (order_number_floor,))
        await db.commit()
    elif row[0] < order_number_floor:
        await db.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'orders'", (order_number_floor,))
        await db.commit()

    # Re-seed default structure if categories empty
    async with db.execute("SELECT COUNT(*) FROM categories") as cursor:
        count = (await cursor.fetchone())[0]

    if count == 0:
        await seed_default_catalog(db)

async def seed_default_catalog(db):
    top_cats = [
        ("Прокси", "🌐"),
        ("Сервисы", "🧩"),
        ("Парсеры", "🔄"),
        ("Карты", "💳"),
        ("Аккаунты", "📊"),
        ("Новинки", "🆕"),
        ("Хиты продаж", "🔥")
    ]

    cat_ids = {}
    for name, emoji in top_cats:
        cursor = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, NULL)", (name, emoji))
        cat_ids[name] = cursor.lastrowid

    # 1. Прокси
    c_mob = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", ("Mobile", "🌐", cat_ids["Прокси"]))
    mobile_id = c_mob.lastrowid

    c_res = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", ("Resident", "⚜️", cat_ids["Прокси"]))
    resident_id = c_res.lastrowid

    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (mobile_id, "Mobile Proxy 30 Days", "📝 Описание:\nСтабильный мобильный прокси для рабочих задач, тестирования и аналитики.\n\n📌 Что входит:\n— Доступ на 30 дней\n— Популярные GEO\n— Помощь при настройке\n\n🛡 Поддержка/гарантия:\nПомощь при настройке", 35.0, 50, "🔥 Хит")
    )
    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (resident_id, "Resident Proxy 30 Days", "📝 Описание:\nРезидентный прокси для аккуратной работы с веб-сервисами.\n\n📌 Что входит:\n— Доступ на 30 дней\n— Стабильный канал\n— Поддержка\n\n🛡 Поддержка/гарантия:\nИндивидуальная проверка", 40.0, 20, "🆕 Новинка")
    )

    # 2. Сервисы
    c_tools = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", ("Tools", "🧩", cat_ids["Сервисы"]))
    tools_id = c_tools.lastrowid

    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (tools_id, "Parser Basic", "📝 Описание:\nНастраиваемый парсер под типовые задачи сбора и структурирования данных.\n\n📌 Что входит:\n— Настройка\n— Инструкция\n— Поддержка запуска\n\n🛡 Поддержка/гарантия:\n7 дней на вопросы по запуску", 120.0, 10, "✅ В наличии")
    )

    # 3. Парсеры
    c_java = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", ("Java", "☕️", cat_ids["Парсеры"]))
    java_id = c_java.lastrowid

    c_py = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", ("Python", "🐍", cat_ids["Парсеры"]))
    py_id = c_py.lastrowid

    c_py_plus = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", ("Python+", "🚀", cat_ids["Парсеры"]))
    py_plus_id = c_py_plus.lastrowid

    c_py_cpp = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", ("Python + C++ Core", "⚡️", cat_ids["Парсеры"]))
    py_cpp_id = c_py_cpp.lastrowid

    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (java_id, "BinHawk • 3 слота", "📝 Описание:\nНаписан на Java. ⚡️ Быстрая работа • 3 рабочих слота • 📖 Инструкция и поддержка\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", 80.0, 10, "🔥 Хит 🦅")
    )
    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (java_id, "BinHawk • 10 слотов", "📝 Описание:\nНаписан на Java. ⚡️ Повышенная производительность • 10 рабочих слотов • 📖 Инструкция и поддержка\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", 90.0, 10, "💎 Premium 🦅")
    )

    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (py_id, "Python Parser • 5 слотов", "📝 Описание:\nНаписан на Python • ⚡️ 5 рабочих слотов • 📊 Стабильная работа • 📖 Поддержка и инструкция\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", 120.0, 9, "🔥 Хит 🐍")
    )
    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (py_id, "Python Parser • 10 слотов", "📝 Описание:\nНаписан на Python • ⚡️ 10 рабочих слотов • 📊 Расширенные возможности • 📖 Поддержка\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", 140.0, 10, "💎 Premium 🐍")
    )

    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (py_plus_id, "Python+ Parser • 10 слотов", "📝 Описание:\n⚡️ Улучшенная версия Python • 🔥 Повышенная скорость • ⚡️ 10 слотов • 💎 Приоритетная поддержка\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", 170.0, 6, "💎 Premium 🚀")
    )

    await db.execute(
        "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
        (py_cpp_id, "C++ Core Parser • 10 слотов", "📝 Описание:\n🚀 Максимальная производительность • Python + C++ Core • ⚡️ 10 слотов • 💎 Премиум решение\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", 210.0, 5, "👑 VIP ⚡️")
    )

    # 4. Карты
    c_cards = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", ("Карты", "", cat_ids["Карты"]))
    cards_id = c_cards.lastrowid

    cards_data = [
        ("Crédit Agricole", 110.0, 15, "✅ В наличии", "Цифровой продукт из раздела карт. Подходит для рабочих задач, где требуется отдельный платёжный инструмент. Перед использованием внимательно ознакомьтесь с правилами магазина."),
        ("La Banque Postale", 110.0, 3, "❌ В наличии", "Позиция временно отсутствует. Можно написать уведомление о поступлении, и бот сообщит, когда товар снова появится."),
        ("Crédit Agricole 2", 100.0, 13, "🔥 Хит", "Популярная позиция в разделе карт. Оптимальный вариант по цене и наличию."),
        ("Deutsche Bank", 65.0, 11, "✅ В наличии", "Базовая позиция в разделе карт с доступной стоимостью и стабильным наличием."),
        ("Sparkasse", 75.0, 6, "🆕 Новинка", "Актуальная позиция в разделе карт. Подходит для тех, кто ищет рабочий вариант со средней стоимостью."),
        ("American Express", 95.0, 15, "✅ В наличии", "Позиция премиального уровня в разделе карт. Перед заказом уточняйте детали у поддержки."),
        ("JPMorgan Chase", 105.0, 10, "✅ В наличии", "Позиция из раздела карт с высоким спросом. Рекомендуется оформлять резерв заранее."),
        ("Bank of America", 105.0, 6, "✅ В наличии", "Позиция временно отсутствует. Можно подписаться на уведомление о поступлении."),
    ]
    for title, price, stock, badge, desc in cards_data:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (cards_id, title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Доступ к позиции после подтверждения заказа\n— Инструкция от менеджера\n— Поддержка по заказу\n\n🛡 Поддержка/гарантия:\nПо правилам магазина и после проверки менеджером", price, stock, badge)
        )

    # 5. Аккаунты
    acc_subcats = [
        ("Ukraine", "🇺🇦"),
        ("USA", "🇺🇸"),
        ("Poland", "🇵🇱"),
        ("Germany", "🇩🇪"),
        ("France", "🇫🇷"),
        ("Автореги", "🌍"),
        ("Premium", "💎"),
        ("Spain Premium", "🇪🇸"),
        ("Italy Premium", "🇮🇹"),
        ("Italy Business", "🇮🇹")
    ]

    acc_ids = {}
    for sub_name, sub_emoji in acc_subcats:
        cur_acc = await db.execute("INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?)", (sub_name, sub_emoji, cat_ids["Аккаунты"]))
        acc_ids[sub_name] = cur_acc.lastrowid

    # 5.1 Ukraine
    ua_prods = [
        ("Ukraine Premium 60D", 25.0, 4, "🔥 Хит", "Тестовый профильный пакет Ukraine для проверки витрины, корзины, резерва, заказов и остатков."),
        ("Ukraine Top 30D", 23.0, 5, "🔥 Хит", "Премиальный тестовый товар Ukraine для проверки ГЕО-папки и статуса HIT."),
        ("Ukraine Lux 12M", 9.07, 6, "💎 Premium", "Тестовый Люкс-пакет Ukraine для проверки премиальных карточек товара."),
        ("Ukraine Starter 21D", 4.0, 6, "✅ В наличии", "Базовый тестовый товар Ukraine для проверки недорогих позиций."),
        ("Ukraine Strong 14D", 9.0, 22, "🔥 Много", "Тестовый товар с большим остатком для проверки отображения наличия."),
        ("Ukraine Manual 14D", 6.0, 13, "✅ В наличии", "Тестовый товар Ukraine для проверки стандартного товара в наличии."),
        ("Ukraine Aged 2Y", 75.0, 11, "💎 Premium", "Дорогой тестовый товар для проверки VIP-заказов, баланса и резерва."),
        ("Ukraine Reserve Pack", 8.33, 2, "⚠️ Осталось мало", "Тестовый товар с маленьким остатком для проверки статуса 'Осталось мало'."),
        ("Ukraine Basic Pack", 6.02, 11, "✅ В наличии", "Базовый тестовый товар Ukraine."),
    ]
    for title, price, stock, badge, desc in ua_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["Ukraine"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Выдача после подтверждения\n— Инструкция\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.2 USA
    usa_prods = [
        ("USA Premium 30D", 25.0, 10, "🔥 Хит", "Тестовый товар для раздела USA."),
        ("USA Basic 7D", 15.0, 10, "✅ В наличии", "Базовый тестовый товар для проверки GEO USA."),
        ("USA Farm 20D", 14.0, 10, "✅ В наличии", "Тестовый товар USA для проверки среднего ценового сегмента."),
        ("USA Starter 7D", 13.0, 10, "✅ В наличии", "Стартовый тестовый товар USA."),
        ("USA VIP 30D", 11.0, 10, "💎 Premium", "Тестовый VIP-товар для USA."),
        ("USA VIP 15D", 10.0, 10, "💎 Premium", "Тестовый VIP-товар USA со средней ценой."),
        ("USA VIP 7D", 9.0, 10, "💎 Premium", "Тестовый VIP-товар USA с низкой ценой."),
    ]
    for title, price, stock, badge, desc in usa_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["USA"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Инструкция\n— Поддержка\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.3 Poland
    pl_prods = [
        ("Poland Premium 30D", 25.0, 10, "🔥 Хит", "Тестовый товар для раздела Poland."),
        ("Poland Basic 7D", 15.0, 10, "✅ В наличии", "Базовый тестовый товар Poland."),
        ("Poland VIP 15D", 11.0, 10, "💎 Premium", "VIP тестовый товар Poland."),
    ]
    for title, price, stock, badge, desc in pl_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["Poland"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Инструкция\n— Поддержка\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.4 Germany
    de_prods = [
        ("🇩🇪 KING👑 1.5 Years old...D", 35.0, 27, "💎 Premium", "KING👑 1.5 Years old ✅ PZRD 🗳 30dayFARM 👤 0-30+ Friend 📸 10+ Foto"),
        ("🇩🇪 KING👑 1 Years old ✅ PZRD", 18.0, 14, "✅ В наличии", "KING👑 1 Years old ✅ PZRD 🗳 30dayFARM 👤 0-30+ Friend 📸 10+ Foto"),
        ("🇩🇪 KING👑 8 Mouth o...D", 14.0, 31, "✅ В наличии", "KING👑 1 Years old ✅ PZRD 🗳 7dayFARM 👤 0-10+ Friend 📸 5+ Foto"),
        ("🇩🇪 KING👑 5 Mouth o...D", 10.0, 37, "✅ В наличии", "KING👑 5 Month old ✅ PZRD 🗳 20dayFARM 👤 0-20+ Friend 📸 15+ Foto"),
        ("🔹 Avtoreg PZRD Trust 🇩🇪", 0.85, 24, "🔥 Хит", "PZRD • Trust • Friend • Ava • Germany"),
        ("🔹 Avtoreg Trust 🇩🇪", 0.95, 33, "✅ В наличии", "Trust • Friend • Ava • Germany"),
        ("🇩🇪 KING 6M PZRD 7D Farm", 13.0, 39, "💎 Premium", "6 Months Old • 7 Day Farm • 5+ Friends • Photos Added"),
    ]
    for title, price, stock, badge, desc in de_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["Germany"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Инструкция\n— Поддержка\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.5 France
    fr_prods = [
        ("France Basic 7D", 13.0, 10, "🆕 Новинка", "Тестовый товар France."),
        ("France VIP 15D", 11.0, 10, "💎 Premium", "VIP тестовый товар France."),
    ]
    for title, price, stock, badge, desc in fr_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["France"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Инструкция\n— Поддержка\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.6 Автореги
    autoreg_prods = [
        ("HIT UA Autoreg Basic", 1.0, 120, "🔥", "Тестовый массовый товар Ukraine для проверки дешевых позиций."),
        ("UA Autoreg Premium", 2.0, 80, "✅ В наличии", "Популярный тестовый товар Ukraine."),
        ("USA Autoreg Basic", 3.0, 60, "✅ В наличии", "Базовый тестовый товар USA."),
        ("PL Autoreg Basic", 2.0, 70, "✅ В наличии", "Базовый тестовый товар Poland."),
        ("DE Autoreg Trust", 0.95, 36, "✅ В наличии", "Базовый тестовый товар Germany."),
        ("HIT DE Autoreg PZRD Trust", 0.85, 47, "🔥", "Тестовый товар Germany с расширенным набором параметров."),
        ("FR Autoreg Basic", 1.0, 90, "✅ В наличии", "Базовый тестовый товар France."),
        ("NEW Mix GEO Starter", 2.0, 100, "🆕", "Смешанный GEO тестовый пакет для проверки каталога."),
    ]
    for title, price, stock, badge, desc in autoreg_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["Автореги"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Пакетная выдача\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.7 Premium
    prem_prods = [
        ("Premium Setup 250", 36.11, 18, "💎", "Премиальный тестовый пакет для проверки дорогих позиций."),
        ("Premium Setup 1500 x2", 118.51, 14, "💎", "Тестовый премиум-пакет с высокой ценой."),
        ("Premium Multi Pack", 137.95, 15, "💎", "Дорогой тестовый товар."),
    ]
    for title, price, stock, badge, desc in prem_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["Premium"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Расширенная поддержка\n— Индивидуальная обработка\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.8 Spain Premium
    es_prods = [
        ("⭐ ES PREMIUM TRUST", 22.0, 12, "💎 Premium", "Испания • 👥 20-120+ друзей • 📄 1-10 фото • 📧 Email • 📱 Отлёжка 30+ дней • 🌱 Ручной фарм • 🚀 Готов к работе"),
        ("🚀 ES BUSINESS READY", 19.0, 15, "🔥 Хит", "Испания • 👥 До 50 друзей • 📄 Создана страница • 📸 3-8 фото • 🖼 Посты • Обложка и аватар • 📧 Email • 📱 Отлёжка 45+ дней • 📸 Фото для подтверждения"),
    ]
    for title, price, stock, badge, desc in es_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["Spain Premium"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.9 Italy Premium
    it_prem_prods = [
        ("⭐ IT TRUST FARM", 16.0, 18, "✅ В наличии", "Италия • 👥 До 50 друзей • 📸 3-8 фото • 🖼 Посты • 📲 Регистрация по номеру • 📧 Email • 🔑 Настройки доступа • 📱 Отлёжка 45+ дней • 📸 Фото для подтверждения"),
        ("💎 IT GOOD PAGE", 14.0, 20, "🔥 Хит", "Италия • 👥 20-120+ друзей • 📄 Страница Good • 📸 Фото • 📧 Email • 🌱 Ручной фарм • 📱 Отлёжка 30+ дней • 📸 Фото для подтверждения"),
    ]
    for title, price, stock, badge, desc in it_prem_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["Italy Premium"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 5.10 Italy Business
    it_biz_prods = [
        ("🏆 IT BUSINESS 2BM", 15.0, 10, "👑 VIP", "Италия • 👤 2 бизнес-профиля • 💰 Лимит 50-250$ • 👥 До 150 друзей • 📧 Email • 🔑 Настройки доступа • 📱 Отлёжка 60+ дней • 📸 Фото для подтверждения"),
    ]
    for title, price, stock, badge, desc in it_biz_prods:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (acc_ids["Italy Business"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Доступ/услуга согласно описанию\n— Поддержка менеджера\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 6. Новинки
    new_items = [
        ("Resident Proxy 30 Days", 40.0, 20, "🆕 Новинка", "Резидентный прокси для аккуратной работы с веб-сервисами."),
        ("Sparkasse", 75.0, 6, "🆕 Новинка", "Актуальная позиция в разделе карт. Подходит для тех, кто ищет рабочий вариант со средней стоимостью."),
        ("France Basic 7D", 13.0, 10, "🆕 Новинка", "Тестовый товар France."),
        ("NEW Mix GEO Starter", 2.0, 100, "🆕", "Смешанный GEO тестовый пакет для проверки каталога."),
    ]
    for title, price, stock, badge, desc in new_items:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (cat_ids["Новинки"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Инструкция\n— Поддержка\n\n🛡 Поддержка/гарантия:\nПо правилам магазина", price, stock, badge)
        )

    # 7. Хиты продаж
    hit_items = [
        ("Mobile Proxy 30 Days", 35.0, 50, "🔥 Хит", "Стабильный мобильный прокси для рабочих задач, тестирования и аналитики."),
        ("BinHawk • 3 слота", 80.0, 10, "🔥 Хит 🦅", "Написан на Java. ⚡️ Быстрая работа • 3 рабочих слота • 📖 Инструкция и поддержка"),
        ("Python Parser • 5 слотов", 120.0, 9, "🔥 Хит 🐍", "Написан на Python • ⚡️ 5 рабочих слотов • 📊 Стабильная работа • 📖 Поддержка и инструкция"),
        ("Crédit Agricole 2", 100.0, 13, "🔥 Хит", "Популярная позиция в разделе карт. Оптимальный вариант по цене и наличию."),
        ("Ukraine Premium 60D", 25.0, 4, "🔥 Хит", "Тестовый профильный пакет Ukraine для проверки витрины."),
        ("Ukraine Top 30D", 23.0, 5, "🔥 Хит", "Премиальный тестовый товар Ukraine для проверки ГЕО-папки."),
        ("Ukraine Strong 14D", 9.0, 22, "🔥 Много", "Тестовый товар с большим остатком."),
        ("USA Premium 30D", 25.0, 10, "🔥 Хит", "Тестовый хит-товар для раздела USA."),
        ("Poland Premium 30D", 25.0, 10, "🔥 Хит", "Тестовый товар для раздела Poland."),
        ("🇩🇪 KING👑 1 Years old ✅ PZRD", 18.0, 14, "✅ В наличии", "KING👑 1 Years old ✅ PZRD 🗳 30dayFARM 👤 0-30+ Friend 📸 10+ Foto"),
        ("🔹 Avtoreg PZRD Trust 🇩🇪", 0.85, 24, "🔥 Хит", "PZRD • Trust • Friend • Ava • Germany"),
        ("🔹 Avtoreg Trust 🇩🇪", 0.95, 33, "✅ В наличии", "Trust • Friend • Ava • Germany"),
        ("HIT UA Autoreg Basic", 1.0, 120, "🔥", "Тестовый массовый товар Ukraine для проверки дешевых позиций."),
        ("HIT DE Autoreg PZRD Trust", 0.85, 47, "🔥", "Тестовый товар Germany с расширенным набором параметров."),
        ("🚀 ES BUSINESS READY", 19.0, 15, "🔥 Хит", "Испания • 👥 До 50 друзей • 📄 Создана страница • 📸 3-8 фото • 🖼 Посты • Обложка и аватар"),
        ("💎 IT GOOD PAGE", 14.0, 20, "🔥 Хит", "Италия • 👥 20-120+ друзей • 📄 Страница Good • 📸 Фото • 📧 Email • 🌱 Ручной фарм"),
    ]
    for title, price, stock, badge, desc in hit_items:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price, stock, badge) VALUES (?, ?, ?, ?, ?, ?)",
            (cat_ids["Хиты продаж"], title, f"📝 Описание:\n{desc}\n\n📌 Что входит:\n— Выдача данных\n— Поддержка", price, stock, badge)
        )

    await db.commit()
    logger.info("Database completely seeded.")

# Helper functions (all share one connection — see get_db)
async def add_user(user_id: int, username: str, first_name: str, ref_id: int = None):
    db = await get_db()
    await db.execute("""
        INSERT INTO users (user_id, username, first_name, ref_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (user_id, username, first_name, ref_id))
    await db.commit()

async def get_user(user_id: int):
    db = await get_db()
    async with db.execute("SELECT user_id, username, first_name, balance, ref_id, created_at FROM users WHERE user_id = ?", (user_id,)) as cursor:
        return await cursor.fetchone()

async def delete_user(user_id: int):
    """Drop a user who blocked the bot so broadcasts stop retrying them."""
    db = await get_db()
    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    await db.commit()

async def get_referrals_count(user_id: int) -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM users WHERE ref_id = ?", (user_id,)) as cursor:
        res = await cursor.fetchone()
        return res[0] if res else 0

async def _get_setting(key: str, default: str) -> str:
    db = await get_db()
    async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else default

async def _set_setting(key: str, value: str):
    db = await get_db()
    await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    await db.commit()

async def get_manager_username() -> str:
    return await _get_setting("manager_username", DEFAULT_MANAGER)

async def set_manager_username(username: str):
    await _set_setting("manager_username", username)

async def get_payment_label() -> str:
    return await _get_setting("payment_label", "Актуальные реквизиты уточняйте у менеджера.")

async def set_payment_label(text: str):
    await _set_setting("payment_label", text)

async def get_payment_address() -> str:
    return await _get_setting("payment_address", "")

async def set_payment_address(text: str):
    await _set_setting("payment_address", text)

async def get_top_categories():
    db = await get_db()
    async with db.execute("SELECT id, name, emoji FROM categories WHERE parent_id IS NULL ORDER BY id ASC") as cursor:
        return await cursor.fetchall()

async def get_subcategories(parent_id: int):
    db = await get_db()
    async with db.execute("SELECT id, name, emoji FROM categories WHERE parent_id = ? ORDER BY id ASC", (parent_id,)) as cursor:
        return await cursor.fetchall()

async def get_category(category_id: int):
    db = await get_db()
    async with db.execute("SELECT id, name, emoji, parent_id FROM categories WHERE id = ?", (category_id,)) as cursor:
        return await cursor.fetchone()

async def add_category(name: str, emoji: str):
    db = await get_db()
    await db.execute("INSERT INTO categories (name, emoji) VALUES (?, ?)", (name, emoji))
    await db.commit()

async def get_products_by_category(category_id: int):
    db = await get_db()
    async with db.execute("SELECT id, title, description, price, stock, badge FROM products WHERE category_id = ? AND is_available = 1 ORDER BY id ASC", (category_id,)) as cursor:
        return await cursor.fetchall()

async def get_product(product_id: int):
    db = await get_db()
    async with db.execute("SELECT id, category_id, title, description, price, stock, badge FROM products WHERE id = ?", (product_id,)) as cursor:
        return await cursor.fetchone()

async def add_product(category_id: int, title: str, description: str, price: float):
    db = await get_db()
    await db.execute(
        "INSERT INTO products (category_id, title, description, price) VALUES (?, ?, ?, ?)",
        (category_id, title, description, price)
    )
    await db.commit()

async def category_exists(category_id: int) -> bool:
    db = await get_db()
    async with db.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)) as cursor:
        return await cursor.fetchone() is not None

async def search_products(query: str):
    db = await get_db()
    # Escape LIKE wildcards so a literal % or _ does not match everything.
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    async with db.execute(
        "SELECT id, title, price, stock, badge FROM products "
        "WHERE (title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\') AND is_available = 1 LIMIT 20",
        (pattern, pattern)
    ) as cursor:
        return await cursor.fetchall()

async def add_to_cart(user_id: int, product_id: int, quantity: int = 1):
    """Add to the cart, stacking onto whatever is already there."""
    db = await get_db()
    await db.execute("""
        INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)
        ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + excluded.quantity
    """, (user_id, product_id, quantity))
    await db.commit()

async def set_cart_quantity(user_id: int, product_id: int, quantity: int):
    """Set an exact quantity; anything below 1 removes the line."""
    db = await get_db()
    if quantity < 1:
        await db.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
    else:
        await db.execute(
            "UPDATE cart SET quantity = ? WHERE user_id = ? AND product_id = ?",
            (quantity, user_id, product_id)
        )
    await db.commit()

async def change_cart_quantity(user_id: int, product_id: int, delta: int) -> int:
    """Nudge a line up or down. Returns the resulting quantity (0 = removed)."""
    db = await get_db()
    async with db.execute(
        "SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return 0
    new_quantity = row[0] + delta
    await set_cart_quantity(user_id, product_id, new_quantity)
    return max(new_quantity, 0)

async def remove_from_cart(user_id: int, product_id: int):
    db = await get_db()
    await db.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
    await db.commit()

async def get_cart_items(user_id: int):
    """Rows of (product_id, title, price, quantity)."""
    db = await get_db()
    async with db.execute("""
        SELECT p.id, p.title, p.price, c.quantity
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
        ORDER BY p.id ASC
    """, (user_id,)) as cursor:
        return await cursor.fetchall()

async def clear_cart(user_id: int):
    db = await get_db()
    await db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
    await db.commit()

async def add_orders(user_id: int, items) -> list[int]:
    """Create every order of a checkout in one transaction.

    `items` is an iterable of (product_id, quantity).
    """
    db = await get_db()
    order_ids = []
    for product_id, quantity in items:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, product_id, quantity) VALUES (?, ?, ?)",
            (user_id, product_id, quantity)
        )
        order_ids.append(cursor.lastrowid)
    await db.commit()
    return order_ids

async def get_user_orders(user_id: int, limit: int = 20):
    db = await get_db()
    async with db.execute("""
        SELECT o.id, p.title, p.price, o.status, o.created_at, o.quantity
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.user_id = ?
        ORDER BY o.id DESC
        LIMIT ?
    """, (user_id, limit)) as cursor:
        return await cursor.fetchall()

async def count_user_orders(user_id: int) -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_all_users_count() -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_all_user_ids():
    db = await get_db()
    async with db.execute("SELECT user_id FROM users") as cursor:
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

async def get_catalog_counts() -> tuple[int, int]:
    """Categories and products in one round trip, for the admin stats screen."""
    db = await get_db()
    async with db.execute(
        "SELECT (SELECT COUNT(*) FROM categories), (SELECT COUNT(*) FROM products)"
    ) as cursor:
        row = await cursor.fetchone()
        return (row[0], row[1]) if row else (0, 0)
