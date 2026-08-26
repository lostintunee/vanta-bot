import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import (
    get_top_categories, get_subcategories, get_category, get_products_by_category,
    get_product, get_manager_username, search_products, add_to_cart, get_cart_items,
    clear_cart, add_orders, get_payment_label, get_payment_address
)
from keyboards import (
    top_categories_keyboard, subcategories_keyboard, products_inline_keyboard,
    product_detail_keyboard, cart_inline_keyboard, order_notification_keyboard
)
from notifications import notify_admins

router = Router()

def format_buyer(user) -> str:
    handle = f"@{user.username}" if user.username else f"<a href='tg://user?id={user.id}'>id{user.id}</a>"
    name = html.escape(user.first_name or "Без имени")
    return f"{name} ({handle})"

async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None):
    """Edit in place, tolerating Telegram's 'message is not modified' complaint.

    Re-tapping a button that leads to the screen already on display (for example
    'Очистить' on an already-empty cart) would otherwise raise.
    """
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise

class SearchState(StatesGroup):
    waiting_for_query = State()

@router.message(F.text.in_(["🛍 Каталог", "💎 Каталог", "Каталог", "/catalog"]))
async def show_catalog(message: Message, state: FSMContext):
    await state.clear()
    categories = await get_top_categories()
    if not categories:
        await message.answer("🛍 <b>Каталог пуст.</b>", parse_mode="HTML")
        return
    await message.answer(
        "🛍 <b>Выберите раздел:</b>",
        reply_markup=top_categories_keyboard(categories),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "back_to_top_cats")
async def callback_back_to_top_cats(callback: CallbackQuery):
    await callback.answer()
    categories = await get_top_categories()
    await safe_edit(
        callback,
        "🛍 <b>Выберите раздел:</b>",
        top_categories_keyboard(categories)
    )

@router.callback_query(F.data.startswith("cat_"))
async def callback_show_category(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[1])
    category = await get_category(category_id)
    if not category:
        await callback.answer("Раздел не найден", show_alert=True)
        return

    await callback.answer()
    cat_id, cat_name, cat_emoji, parent_id = category
    cat_header = f"{cat_emoji} {cat_name}" if cat_emoji else cat_name

    # Check if this category has subcategories
    subcats = await get_subcategories(cat_id)
    if subcats:
        await safe_edit(
            callback,
            f"{html.escape(cat_header)}\nВыберите папку:",
            subcategories_keyboard(cat_id, subcats)
        )
        return

    # If no subcategories, load products directly
    products = await get_products_by_category(cat_id)
    if not products:
        await safe_edit(
            callback,
            f"{html.escape(cat_header)}\nВ этой папке пока нет товаров.",
            products_inline_keyboard(parent_id, [])
        )
        return

    await safe_edit(
        callback,
        f"{html.escape(cat_header)}\nВыберите товар:",
        products_inline_keyboard(parent_id, products)
    )

@router.callback_query(F.data.startswith("prod_"))
async def callback_show_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await callback.answer()
    p_id, cat_id, title, desc, price, stock, badge = product
    manager = await get_manager_username()

    badge_text = f"{badge} " if badge else ""
    stock_text = f"🔥 Много в наличии: {stock}" if stock >= 20 else f"✅ В наличии: {stock}"

    text = (
        f"<b>{badge_text}{html.escape(title)}</b>\n\n"
        f"<b>Описание:</b>\n{html.escape(desc or '')}\n\n"
        f"<b>Цена:</b> {price:.1f}$\n"
        f"<b>Наличие:</b> {stock_text}"
    )

    await safe_edit(callback, text, product_detail_keyboard(p_id, cat_id, manager))

@router.callback_query(F.data.startswith("addcart_"))
async def callback_add_cart(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    await add_to_cart(user_id, product_id)
    await callback.answer("✅ Товар добавлен в корзину!", show_alert=True)

@router.callback_query(F.data.startswith("interest_"))
async def callback_product_interest(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    p_id, cat_id, title, desc, price, stock, badge = product
    manager = await get_manager_username()
    clean_manager = manager.replace("@", "")

    text = (
        "📨 <b>Запрос по товару</b>\n\n"
        f"👤 Клиент: {format_buyer(callback.from_user)}\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n\n"
        f"📦 Товар: <b>{html.escape(title)}</b> (ID <code>{p_id}</code>)\n"
        f"💰 Цена: {price:.2f}$"
    )
    await notify_admins(
        callback.bot, text,
        order_notification_keyboard(callback.from_user.id, "✉️ Написать клиенту")
    )
    await callback.answer("✅ Запрос отправлен менеджеру! Напишите ему, чтобы обсудить детали.", show_alert=True)
    await callback.message.answer(
        f"👨‍💻 Менеджер уведомлен о вашем интересе к «{html.escape(title)}».\n"
        f"Напишите ему напрямую: <a href='https://t.me/{clean_manager}'>{html.escape(manager)}</a>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(F.text.in_(["🛒 Корзина", "Корзина"]))
async def show_cart(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    items = await get_cart_items(user_id)

    if not items:
        await message.answer(
            "🛒 <b>Корзина пустая.</b>",
            reply_markup=cart_inline_keyboard(cart_empty=True),
            parse_mode="HTML"
        )
        return

    total = sum(item[2] for item in items)
    cart_text = "🛒 <b>Ваша корзина:</b>\n\n"
    for idx, (p_id, title, price) in enumerate(items, 1):
        cart_text += f"{idx}. <b>{html.escape(title)}</b> — {price:.1f}$\n"
    cart_text += f"\n💰 <b>Итого:</b> {total:.1f}$"

    await message.answer(
        cart_text,
        reply_markup=cart_inline_keyboard(cart_empty=False),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "cart_checkout_empty")
async def callback_cart_empty_checkout(callback: CallbackQuery):
    await callback.answer("Корзина пустая!", show_alert=True)

@router.callback_query(F.data == "checkout_cart")
async def callback_checkout_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    items = await get_cart_items(user_id)
    if not items:
        await callback.answer("Корзина пустая!", show_alert=True)
        return

    order_ids = await add_orders(user_id, [p_id for p_id, _, _ in items])
    total = sum(item[2] for item in items)
    items_lines = "\n".join(f"• {html.escape(title)} — {price:.2f}$" for _, title, price in items)
    order_tags = ", ".join(f"#{oid}" for oid in order_ids)

    notify_text = (
        "🛒 <b>Новый заказ!</b>\n\n"
        f"👤 Клиент: {format_buyer(callback.from_user)}\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n\n"
        f"{items_lines}\n\n"
        f"💰 <b>Итого: {total:.2f}$</b>\n"
        f"🔖 Заказы: {order_tags}"
    )
    await notify_admins(callback.bot, notify_text, order_notification_keyboard(user_id))
    await clear_cart(user_id)

    manager = await get_manager_username()
    clean_manager = manager.replace("@", "")
    payment_label = await get_payment_label()
    payment_address = await get_payment_address()

    requisites_block = f"💳 <b>Реквизиты для оплаты:</b>\n{html.escape(payment_label)}"
    if payment_address:
        requisites_block += f"\n<code>{html.escape(payment_address)}</code>"

    await callback.message.edit_text(
        f"✅ <b>Заказ оформлен!</b> ({order_tags})\n\n"
        f"{items_lines}\n\n"
        f"💰 <b>К оплате: {total:.2f}$</b>\n\n"
        f"{requisites_block}\n\n"
        f"После перевода напишите менеджеру для подтверждения: "
        f"<a href='https://t.me/{clean_manager}'>{html.escape(manager)}</a>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "clear_cart")
async def callback_clear_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    await clear_cart(user_id)
    await callback.answer("🗑 Корзина очищена!", show_alert=True)
    await safe_edit(callback, "🛒 <b>Корзина пустая.</b>", cart_inline_keyboard(cart_empty=True))

@router.callback_query(F.data == "promocode")
async def callback_promocode(callback: CallbackQuery):
    await callback.answer("🎟 У вас нет активных промокодов.", show_alert=True)

# Search functionality
@router.message(F.text.in_(["🔎 Поиск", "🔍 Поиск", "Поиск"]))
async def start_search(message: Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_query)
    await message.answer("🔎 <b>Введите название или часть описания товара.</b>", parse_mode="HTML")

@router.message(SearchState.waiting_for_query)
async def process_search(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("🔎 Введите текстовый запрос — например, название товара.")
        return
    await state.clear()

    results = await search_products(query)
    if not results:
        await message.answer(f"🔎 По запросу «<b>{html.escape(query)}</b>» ничего не найдено.", parse_mode="HTML")
        return

    text = f"🔎 <b>Результаты поиска:</b>"
    buttons = []
    for p_id, title, price, stock, badge in results:
        badge_text = f"{badge} " if badge else ""
        btn_text = f"{badge_text}{title} | {price:.1f}$"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"prod_{p_id}")])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_top_cats")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
