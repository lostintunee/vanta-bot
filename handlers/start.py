import html
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from database import add_user, get_user, get_referrals_count, get_manager_username, get_user_orders
from keyboards import main_reply_keyboard, balance_inline_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Гость"
    
    # Check referral
    ref_id = None
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            potential_ref = int(args[1].replace("ref_", ""))
            if potential_ref != user_id:
                ref_id = potential_ref
        except ValueError:
            pass

    await add_user(user_id, username, first_name, ref_id)
    
    welcome_text = (
        "👋 <b>Добро пожаловать в VANTA Shop!</b>\n\n"
        "Выберите нужный раздел, добавьте товар в корзину и оформите заказ.\n"
        "Если возникнут вопросы — поддержка всегда рядом."
    )
    await message.answer(welcome_text, reply_markup=main_reply_keyboard(), parse_mode="HTML")

@router.message(F.text.in_(["📜 Правила", "Правила"]))
async def show_rules(message: Message):
    rules_text = (
        "📜 <b>Правила магазина VANTA Shop</b>\n\n"
        "1. Перед заказом внимательно проверяйте состав корзины.\n"
        "2. Резерв товара действует ограниченное время после оформления.\n"
        "3. После оплаты отправьте подтверждение или скриншот менеджеру.\n"
        "4. Заявки на замену невалидных позиций принимаются в течение 24 часов."
    )
    await message.answer(rules_text, parse_mode="HTML")

@router.message(F.text.in_(["🛡 Гарантии", "Гарантии"]))
async def show_guarantees(message: Message):
    manager = await get_manager_username()
    clean_manager = manager.replace("@", "")
    guarantees_text = (
        "🛡 <b>Гарантии и Безопасность VANTA Shop</b>\n\n"
        "✅ <b>Валидация перед выдачей</b> — все позиции проверяются перед передачей клиенту.\n"
        "🔄 <b>Замена 24/7</b> — при возникновении невалида замена производится в кратчайшие сроки.\n"
        "🔒 <b>Конфиденциальность</b> — полная анонимность сделок и защита данных клиентов.\n\n"
        f"👨‍💻 <b>Прямой контакт поддержки:</b> <a href='https://t.me/{clean_manager}'>{html.escape(manager)}</a>"
    )
    await message.answer(guarantees_text, parse_mode="HTML", disable_web_page_preview=True)

@router.message(F.text.in_(["🤖 Support", "👨‍💻 Менеджер", "Support", "Менеджер", "Поддержка"]))
async def show_support(message: Message):
    manager = await get_manager_username()
    clean_manager = manager.replace("@", "")
    await message.answer(
        f"🤖 <b>Служба поддержки:</b> <a href='https://t.me/{clean_manager}'>{html.escape(manager)}</a>\n\n"
        "Напишите менеджеру для оформления заказа, пополнения баланса или решения любых вопросов.",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(F.text.in_(["♻️ Замена товара", "Замена товара", "Замена"]))
async def show_replacement(message: Message):
    manager = await get_manager_username()
    clean_manager = manager.replace("@", "")
    await message.answer(
        f"♻️ <b>Замена товара:</b> Для оформления заявки на замену напишите менеджеру <a href='https://t.me/{clean_manager}'>{html.escape(manager)}</a> с указанием номера вашего заказа.",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(F.text.in_(["💰 Баланс", "💼 Профиль & Баланс", "Профиль", "Баланс", "Профиль & Баланс"]))
async def show_balance(message: Message):
    user_id = message.from_user.id
    user_data = await get_user(user_id)
    ref_count = await get_referrals_count(user_id)
    manager = await get_manager_username()
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username or "vanta_bot"

    balance = user_data[3] if user_data else 0.0

    profile_text = (
        f"💰 <b>Баланс: {balance:.1f}$</b>\n"
        f"🎖 <b>Уровень: Новичок</b>\n"
        f"👥 <b>Рефералов: {ref_count}</b>"
    )
    await message.answer(
        profile_text, 
        reply_markup=balance_inline_keyboard(manager, bot_username, user_id),
        parse_mode="HTML"
    )

@router.message(F.text.in_(["📦 Мои заказы", "Мои заказы", "Заказы"]))
async def show_my_orders(message: Message):
    user_id = message.from_user.id
    orders = await get_user_orders(user_id)
    if not orders:
        await message.answer("У вас пока нет заказов.", parse_mode="HTML")
        return
    
    text = "📦 <b>История ваших заказов:</b>\n\n"
    for order_id, title, price, status, created_at in orders:
        text += f"🔹 <b>Заказ #{order_id}</b>\n"
        text += f"Товар: {html.escape(title)}\n"
        text += f"Сумма: {price:.1f}$ | Статус: <code>{status}</code>\n"
        text += f"Дата: {created_at}\n\n"
    
    await message.answer(text, parse_mode="HTML")
