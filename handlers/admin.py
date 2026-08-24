import html
import aiosqlite
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_IDS, DB_PATH
from database import (
    get_all_users_count, get_all_user_ids, set_manager_username,
    get_top_categories, get_manager_username, get_payment_requisites, set_payment_requisites
)
from keyboards import admin_reply_keyboard, main_reply_keyboard

router = Router()

class AddCategoryState(StatesGroup):
    name = State()
    emoji = State()

class AddProductState(StatesGroup):
    category_id = State()
    title = State()
    description = State()
    price = State()

class SetManagerState(StatesGroup):
    username = State()

class SetRequisitesState(StatesGroup):
    text = State()

class BroadcastState(StatesGroup):
    text = State()

def is_admin(user_id: int) -> bool:
    # If no specific ADMIN_IDS set or default placeholder, check against config
    if not ADMIN_IDS or ADMIN_IDS == [123456789]:
        # Return False by default to restrict unauthorized access, or match list
        return user_id in ADMIN_IDS
    return user_id in ADMIN_IDS

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ У вас нет прав доступа к админ-панели.")
        return
    await message.answer("⚙️ <b>Панель администратора</b>", reply_markup=admin_reply_keyboard(), parse_mode="HTML")

@router.message(F.text == "🏠 Выход из админки")
async def exit_admin(message: Message):
    await message.answer("🏠 Вы вышли из админ-панели.", reply_markup=main_reply_keyboard())

@router.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    users_count = await get_all_users_count()
    manager = await get_manager_username()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM categories") as c1:
            cats_count = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM products") as c2:
            prods_count = (await c2.fetchone())[0]

    stats_text = (
        "📊 <b>Статистика Бота:</b>\n\n"
        f"👤 Всего пользователей: <code>{users_count}</code>\n"
        f"📁 Категорий и папок: <code>{cats_count}</code>\n"
        f"📌 Товаров: <code>{prods_count}</code>\n"
        f"👨‍💻 Менеджер: <code>{html.escape(manager)}</code>"
    )
    await message.answer(stats_text, parse_mode="HTML")

@router.message(F.text == "⚙️ Настроить менеджера")
async def start_set_manager(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(SetManagerState.username)
    current = await get_manager_username()
    await message.answer(
        f"⚙️ Текущий юзернейм менеджера: <code>{html.escape(current)}</code>\n\n"
        "Введите новый юзернейм в формате <code>@username</code>:",
        parse_mode="HTML"
    )

@router.message(SetManagerState.username)
async def process_set_manager(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    new_username = message.text.strip()
    if not new_username.startswith("@"):
        new_username = "@" + new_username
    await set_manager_username(new_username)
    await state.clear()
    await message.answer(f"✅ Менеджер успешно изменен на <code>{html.escape(new_username)}</code>!", reply_markup=admin_reply_keyboard(), parse_mode="HTML")

@router.message(F.text == "💳 Реквизиты оплаты")
async def start_set_requisites(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(SetRequisitesState.text)
    current = await get_payment_requisites()
    await message.answer(
        f"💳 Текущие реквизиты:\n<code>{html.escape(current)}</code>\n\n"
        "Отправьте новый текст реквизитов (кошелёк, карта, банк — что угодно). "
        "Этот текст будет показываться клиенту при оформлении заказа:",
        parse_mode="HTML"
    )

@router.message(SetRequisitesState.text)
async def process_set_requisites(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    new_text = message.text.strip()
    await set_payment_requisites(new_text)
    await state.clear()
    await message.answer(
        f"✅ Реквизиты оплаты обновлены:\n<code>{html.escape(new_text)}</code>",
        reply_markup=admin_reply_keyboard(),
        parse_mode="HTML"
    )

@router.message(F.text == "📁 Добавить категорию")
async def start_add_category(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AddCategoryState.name)
    await message.answer("📁 Введите название новой категории:")

@router.message(AddCategoryState.name)
async def process_cat_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AddCategoryState.emoji)
    await message.answer("Введите значок/эмодзи категории:")

@router.message(AddCategoryState.emoji)
async def process_cat_emoji(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    cat_name = data["name"]
    emoji = message.text.strip()
    await state.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO categories (name, emoji) VALUES (?, ?)", (cat_name, emoji))
        await db.commit()

    await message.answer(f"✅ Категория «{html.escape(emoji)} {html.escape(cat_name)}» добавлена!", reply_markup=admin_reply_keyboard(), parse_mode="HTML")

@router.message(F.text == "➕ Добавить оффер")
async def start_add_product(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    categories = await get_top_categories()
    if not categories:
        await message.answer("❌ Сначала создайте категорию!")
        return

    cat_list = "\n".join([f"ID <code>{c[0]}</code>: {c[2]} {html.escape(c[1])}" for c in categories])
    await state.set_state(AddProductState.category_id)
    await message.answer(
        f"📋 Список категорий:\n{cat_list}\n\nВведите <b>ID категории</b> для товара:",
        parse_mode="HTML"
    )

@router.message(AddProductState.category_id)
async def process_prod_cat_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID категории:")
        return
    await state.update_data(category_id=int(message.text.strip()))
    await state.set_state(AddProductState.title)
    await message.answer("📌 Введите название товара:")

@router.message(AddProductState.title)
async def process_prod_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(AddProductState.description)
    await message.answer("📝 Введите описание товара:")

@router.message(AddProductState.description)
async def process_prod_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(AddProductState.price)
    await message.answer("💵 Введите цену в USD (например: 35.0):")

@router.message(AddProductState.price)
async def process_prod_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("❌ Неверный формат цены. Введите число:")
        return

    data = await state.get_data()
    await state.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO products (category_id, title, description, price) VALUES (?, ?, ?, ?)",
            (data["category_id"], data["title"], data["description"], price)
        )
        await db.commit()

    await message.answer(f"✅ Товар «<b>{html.escape(data['title'])}</b>» за <code>{price:.1f}$</code> добавлен!", reply_markup=admin_reply_keyboard(), parse_mode="HTML")

@router.message(F.text == "📢 Рассылка")
async def start_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.text)
    await message.answer("📢 Введите текст для рассылки:")

@router.message(BroadcastState.text)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text
    await state.clear()

    user_ids = await get_all_user_ids()
    sent_count = 0
    fail_count = 0

    await message.answer("🚀 Рассылка запущена...")
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, text, parse_mode="HTML")
            sent_count += 1
        except Exception:
            fail_count += 1

    await message.answer(
        f"✅ <b>Рассылка завершена!</b>\n\nДоставлено: <code>{sent_count}</code>\nОшибок: <code>{fail_count}</code>",
        reply_markup=admin_reply_keyboard(),
        parse_mode="HTML"
    )
