import asyncio
import html
import logging
from aiogram import Router, F
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_IDS, STAFF_IDS, BROADCAST_DELAY
from database import (
    get_all_users_count, get_all_user_ids, set_manager_username,
    get_top_categories, get_manager_username, get_payment_label, get_payment_address,
    set_payment_label, set_payment_address, get_user, add_category, add_product,
    category_exists, get_catalog_counts, delete_user
)
from keyboards import admin_reply_keyboard, main_reply_keyboard, delivery_mode_keyboard

logger = logging.getLogger(__name__)

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
    label = State()
    address = State()

class BroadcastState(StatesGroup):
    text = State()

class DeliverState(StatesGroup):
    user_id = State()
    content = State()

def is_staff(user_id: int) -> bool:
    """Owners plus the manager — everyone allowed to hand orders to clients."""
    return user_id in STAFF_IDS

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def require_text(message: Message) -> str | None:
    """Return trimmed text, or tell the sender off for non-text input."""
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Здесь нужен текст. Попробуйте ещё раз:")
        return None
    return text

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ У вас нет прав доступа к админ-панели.")
        return
    await message.answer("⚙️ <b>Панель администратора</b>", reply_markup=admin_reply_keyboard(), parse_mode="HTML")

@router.message(F.text == "🏠 Выход из админки")
async def exit_admin(message: Message, state: FSMContext):
    # Clear any pending flow so leaving never strands staff mid-delivery.
    await state.clear()
    await message.answer("🏠 Вы вышли из админ-панели.", reply_markup=main_reply_keyboard())

@router.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    users_count = await get_all_users_count()
    manager = await get_manager_username()
    cats_count, prods_count = await get_catalog_counts()

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
    new_username = await require_text(message)
    if new_username is None:
        return
    if not new_username.startswith("@"):
        new_username = "@" + new_username
    await set_manager_username(new_username)
    await state.clear()
    await message.answer(f"✅ Менеджер успешно изменен на <code>{html.escape(new_username)}</code>!", reply_markup=admin_reply_keyboard(), parse_mode="HTML")

@router.message(F.text == "💳 Реквизиты оплаты")
async def start_set_requisites(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(SetRequisitesState.label)
    current_label = await get_payment_label()
    current_address = await get_payment_address()
    await message.answer(
        f"💳 Текущее описание:\n{html.escape(current_label)}\n\n"
        f"💳 Текущий адрес/номер:\n<code>{html.escape(current_address) or '(не задан)'}</code>\n\n"
        "Шаг 1/2. Пришлите текст-описание способа оплаты (например: <code>USDT (сеть TRC20 / Tron)</code>, "
        "можно с любыми пояснениями и предупреждениями). Сам адрес/номер счёта сюда не пишите — его спросим отдельно, "
        "чтобы клиент мог скопировать одним тапом только его:",
        parse_mode="HTML"
    )

@router.message(SetRequisitesState.label)
async def process_set_requisites_label(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    label = await require_text(message)
    if label is None:
        return
    await state.update_data(label=label)
    await state.set_state(SetRequisitesState.address)
    await message.answer(
        "Шаг 2/2. Теперь пришлите сам адрес кошелька / номер карты / счёт — "
        "именно этот текст будет выделен моноширинным шрифтом и копироваться одним тапом:"
    )

@router.message(SetRequisitesState.address)
async def process_set_requisites_address(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    address = await require_text(message)
    if address is None:
        return
    data = await state.get_data()
    label = data["label"]
    await set_payment_label(label)
    await set_payment_address(address)
    await state.clear()
    await message.answer(
        f"✅ Реквизиты оплаты обновлены:\n{html.escape(label)}\n<code>{html.escape(address)}</code>",
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
    name = await require_text(message)
    if name is None:
        return
    await state.update_data(name=name)
    await state.set_state(AddCategoryState.emoji)
    await message.answer("Введите значок/эмодзи категории:")

@router.message(AddCategoryState.emoji)
async def process_cat_emoji(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    emoji = await require_text(message)
    if emoji is None:
        return
    data = await state.get_data()
    cat_name = data["name"]
    await state.clear()

    await add_category(cat_name, emoji)

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
    raw = await require_text(message)
    if raw is None:
        return
    if not raw.isdigit():
        await message.answer("❌ Введите числовой ID категории:")
        return
    if not await category_exists(int(raw)):
        await message.answer("❌ Категории с таким ID нет. Введите ID из списка выше:")
        return
    await state.update_data(category_id=int(raw))
    await state.set_state(AddProductState.title)
    await message.answer("📌 Введите название товара:")

@router.message(AddProductState.title)
async def process_prod_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    title = await require_text(message)
    if title is None:
        return
    await state.update_data(title=title)
    await state.set_state(AddProductState.description)
    await message.answer("📝 Введите описание товара:")

@router.message(AddProductState.description)
async def process_prod_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    description = await require_text(message)
    if description is None:
        return
    await state.update_data(description=description)
    await state.set_state(AddProductState.price)
    await message.answer("💵 Введите цену в USD (например: 35.0):")

@router.message(AddProductState.price)
async def process_prod_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = await require_text(message)
    if raw is None:
        return
    try:
        price = float(raw.replace(",", "."))
    except ValueError:
        await message.answer("❌ Неверный формат цены. Введите число:")
        return
    if price < 0:
        await message.answer("❌ Цена не может быть отрицательной. Введите число:")
        return

    data = await state.get_data()
    await state.clear()

    await add_product(data["category_id"], data["title"], data["description"], price)

    await message.answer(f"✅ Товар «<b>{html.escape(data['title'])}</b>» за <code>{price:.1f}$</code> добавлен!", reply_markup=admin_reply_keyboard(), parse_mode="HTML")

async def enter_delivery_mode(message: Message, state: FSMContext, target_id: int):
    """Put staff into the mode where everything they send is forwarded to one client."""
    target = await get_user(target_id)
    if target:
        target_name = html.escape(target[2] or "Без имени")
        who = f"{target_name} (@{target[1]})" if target[1] else target_name
        known = f"👤 Получатель: {who}\n🆔 ID: <code>{target_id}</code>"
    else:
        known = (
            f"🆔 ID: <code>{target_id}</code>\n"
            "⚠️ Этого пользователя нет в базе бота — доставка может не пройти."
        )

    await state.set_state(DeliverState.content)
    await state.update_data(target_id=target_id, sent_count=0, header_sent=False)
    await message.answer(
        f"📤 <b>Режим выдачи</b>\n\n{known}\n\n"
        "Отправляйте сюда что угодно — текст, фото, документы, архивы. "
        "Каждое сообщение будет сразу переслано клиенту от имени бота.\n\n"
        "Когда закончите — нажмите «✅ Завершить выдачу».",
        reply_markup=delivery_mode_keyboard(),
        parse_mode="HTML"
    )

@router.message(F.text == "📤 Выдать заказ")
async def start_deliver(message: Message, state: FSMContext):
    if not is_staff(message.from_user.id):
        return
    await state.set_state(DeliverState.user_id)
    await message.answer(
        "📤 Введите <b>ID клиента</b>, которому нужно отправить заказ.\n\n"
        "ID есть в уведомлении о заказе — его можно скопировать одним тапом.",
        parse_mode="HTML"
    )

@router.message(DeliverState.user_id)
async def process_deliver_user_id(message: Message, state: FSMContext):
    if not is_staff(message.from_user.id):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("❌ ID должен быть числом. Введите ID клиента ещё раз:")
        return
    await enter_delivery_mode(message, state, int(raw))

@router.callback_query(F.data.startswith("deliver_"))
async def callback_start_deliver(callback: CallbackQuery, state: FSMContext):
    if not is_staff(callback.from_user.id):
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    target_id = int(callback.data.split("_")[1])
    await callback.answer()
    await enter_delivery_mode(callback.message, state, target_id)

@router.message(DeliverState.content, F.text == "✅ Завершить выдачу")
async def finish_deliver(message: Message, state: FSMContext):
    if not is_staff(message.from_user.id):
        return
    data = await state.get_data()
    sent_count = data.get("sent_count", 0)
    await state.clear()
    await message.answer(
        f"✅ Выдача завершена. Отправлено сообщений: <code>{sent_count}</code>.",
        reply_markup=admin_reply_keyboard(),
        parse_mode="HTML"
    )

@router.message(DeliverState.content)
async def process_deliver_content(message: Message, state: FSMContext):
    if not is_staff(message.from_user.id):
        return
    data = await state.get_data()
    target_id = data["target_id"]

    try:
        if not data.get("header_sent"):
            await message.bot.send_message(
                target_id,
                "📦 <b>Ваш заказ от VANTA Shop</b>\n\nНиже — материалы по вашему заказу.",
                parse_mode="HTML"
            )
            await state.update_data(header_sent=True)

        await message.copy_to(chat_id=target_id)
    except Exception as exc:
        logger.exception(f"Delivery to {target_id} failed")
        await message.answer(
            "❌ <b>Не доставлено.</b>\n\n"
            f"Причина: <code>{html.escape(str(exc))}</code>\n\n"
            "Обычно это значит, что клиент не запускал бота или заблокировал его.",
            parse_mode="HTML"
        )
        return

    sent_count = data.get("sent_count", 0) + 1
    await state.update_data(sent_count=sent_count)
    await message.answer(f"✅ Доставлено клиенту ({sent_count}).")

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
    text = await require_text(message)
    if text is None:
        return
    await state.clear()

    user_ids = await get_all_user_ids()
    sent_count = 0
    fail_count = 0
    dropped = []

    await message.answer(f"🚀 Рассылка запущена — получателей: {len(user_ids)}...")
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, text, parse_mode="HTML")
            sent_count += 1
        except TelegramRetryAfter as exc:
            # Telegram told us the exact backoff; honour it and retry once.
            await asyncio.sleep(exc.retry_after)
            try:
                await message.bot.send_message(uid, text, parse_mode="HTML")
                sent_count += 1
            except Exception:
                fail_count += 1
        except Exception as exc:
            fail_count += 1
            if "bot was blocked" in str(exc) or "user is deactivated" in str(exc) or "chat not found" in str(exc):
                dropped.append(uid)
        # Stay under Telegram's ~30 msg/sec ceiling.
        await asyncio.sleep(BROADCAST_DELAY)

    for uid in dropped:
        await delete_user(uid)

    summary = (
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"Доставлено: <code>{sent_count}</code>\nОшибок: <code>{fail_count}</code>"
    )
    if dropped:
        summary += f"\nУдалено неактивных: <code>{len(dropped)}</code>"

    await message.answer(summary, reply_markup=admin_reply_keyboard(), parse_mode="HTML")
