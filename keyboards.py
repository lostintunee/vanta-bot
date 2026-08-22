from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="🔎 Поиск")],
            [KeyboardButton(text="🛒 Корзина"), KeyboardButton(text="📦 Мои заказы")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📜 Правила")],
            [KeyboardButton(text="♻️ Замена товара"), KeyboardButton(text="🤖 Support")]
        ],
        resize_keyboard=True
    )

def top_categories_keyboard(categories) -> InlineKeyboardMarkup:
    buttons = []
    for cat_id, cat_name, cat_emoji in categories:
        text = f"{cat_emoji} {cat_name}" if cat_emoji else cat_name
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"cat_{cat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def subcategories_keyboard(parent_id: int, subcats) -> InlineKeyboardMarkup:
    buttons = []
    for s_id, s_name, s_emoji in subcats:
        text = f"📁 {s_emoji} {s_name}" if s_emoji else f"📁 {s_name}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"cat_{s_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_top_cats")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def products_inline_keyboard(parent_category_id: int, products) -> InlineKeyboardMarkup:
    buttons = []
    for p_id, p_title, p_desc, p_price, p_stock, p_badge in products:
        if p_stock <= 5:
            stock_text = f"⚠️ Осталось мало: {p_stock}"
        elif p_stock >= 20:
            stock_text = f"🔥 Много в наличии: {p_stock}"
        else:
            stock_text = f"✅ В наличии: {p_stock}"

        badge_text = f"{p_badge} " if p_badge else ""
        btn_text = f"{badge_text}{p_title} | {p_price:.2f}$ | {stock_text}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"prod_{p_id}")])
    
    back_target = f"cat_{parent_category_id}" if parent_category_id else "back_to_top_cats"
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_target)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def product_detail_keyboard(product_id: int, category_id: int, manager_username: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📲 Связаться с менеджером", callback_data=f"interest_{product_id}")],
        [InlineKeyboardButton(text="➕ Добавить в корзину", callback_data=f"addcart_{product_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat_{category_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cart_inline_keyboard(cart_empty: bool = False) -> InlineKeyboardMarkup:
    if cart_empty:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Оформить", callback_data="cart_checkout_empty"), InlineKeyboardButton(text="🗑 Очистить", callback_data="clear_cart")],
            [InlineKeyboardButton(text="🎟 Промокод", callback_data="promocode")],
            [InlineKeyboardButton(text="🛍 В каталог", callback_data="back_to_top_cats")]
        ])

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оформить", callback_data="checkout_cart"), InlineKeyboardButton(text="🗑 Очистить", callback_data="clear_cart")],
        [InlineKeyboardButton(text="🎟 Промокод", callback_data="promocode")],
        [InlineKeyboardButton(text="🛍 В каталог", callback_data="back_to_top_cats")]
    ])

def balance_inline_keyboard(manager_username: str, bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    clean_manager = manager_username.replace("@", "")
    deposit_url = f"https://t.me/{clean_manager}?text=Здравствуйте!%20Хочу%20пополнить%20баланс%20в%20боте%20(ID:%20{user_id})"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if bot_username else "#"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Заявка на пополнение", url=deposit_url)],
        [InlineKeyboardButton(text="🔗 Моя реф-ссылка", switch_inline_query=ref_link)]
    ])

def admin_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить оффер"), KeyboardButton(text="📁 Добавить категорию")],
            [KeyboardButton(text="⚙️ Настроить менеджера"), KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🏠 Выход из админки")]
        ],
        resize_keyboard=True
    )
