from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PhotoSize, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.keyboards.buttons import main_menu, confirm_barcode
from app.database.db import get_product_by_name, save_history, search_open_food_facts, get_user_history, add_product
import os
import io

try:
    from PIL import Image
    from pyzbar.pyzbar import decode
    BARCODE_ENABLED = True
except ImportError:
    BARCODE_ENABLED = False

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

class CheckProduct(StatesGroup):
    waiting_barcode = State()
    waiting_photo = State()
    waiting_manual_name = State()

def admin_keyboard(name: str, brand: str, user_id: int):
    safe_name = name.replace(":", "_").replace("|", "_")[:30]
    safe_brand = brand.replace(":", "_").replace("|", "_")[:20]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Халал", callback_data=f"setstatus:halal:{user_id}:{safe_name}:{safe_brand}"),
            InlineKeyboardButton(text="❌ Харам", callback_data=f"setstatus:haram:{user_id}:{safe_name}:{safe_brand}"),
            InlineKeyboardButton(text="⚠️ Сомнит.", callback_data=f"setstatus:doubtful:{user_id}:{safe_name}:{safe_brand}"),
        ]
    ])

@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🕌 Assalamu Alaikum!\n\n"
        "Добро пожаловать в Halal Food Checker!\n\n"
        "Этот бот поможет тебе узнать халяльность продукта по штрихкоду.\n\n"
        "👨‍💻 Разработчик: <b>Kurban Polatov</b>\n\n"
        "Отправь штрихкод товара — узнаем халяль он или нет.",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

@router.message(F.text == "⌨️ Ввести вручную")
async def manual_input(message: Message, state: FSMContext):
    await state.set_state(CheckProduct.waiting_barcode)
    await message.answer("Введи штрихкод товара (цифры с упаковки):")

@router.message(F.text == "📷 Фото штрихкода")
async def photo_input(message: Message, state: FSMContext):
    await state.set_state(CheckProduct.waiting_photo)
    await message.answer("📷 Отправь фото штрихкода:")

@router.message(CheckProduct.waiting_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    if not BARCODE_ENABLED:
        await state.clear()
        await message.answer("❌ Распознавание фото недоступно. Введи штрихкод вручную.", reply_markup=main_menu())
        return
    await state.clear()
    photo: PhotoSize = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    image = Image.open(io.BytesIO(file_bytes.read()))
    barcodes = decode(image)
    if not barcodes:
        await message.answer("❌ Штрихкод не найден. Попробуй ещё раз или введи вручную.", reply_markup=main_menu())
        return
    barcode = barcodes[0].data.decode("utf-8")
    await state.update_data(barcode=barcode)
    await message.answer(
        f"Штрихкод найден: <code>{barcode}</code>\nЭто правильно?",
        reply_markup=confirm_barcode(barcode),
        parse_mode="HTML"
    )

@router.message(CheckProduct.waiting_barcode)
async def process_barcode(message: Message, state: FSMContext):
    barcode = message.text.strip()
    await state.clear()
    await state.update_data(barcode=barcode)
    await message.answer(
        f"Штрихкод: <code>{barcode}</code>\nЭто правильно?",
        reply_markup=confirm_barcode(barcode),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("confirm_"))
async def confirmed_barcode(callback: CallbackQuery, state: FSMContext):
    barcode = callback.data.replace("confirm_", "")
    await state.update_data(barcode=barcode)
    await callback.message.edit_text("🔍 Ищем товар...")
    off_product = await search_open_food_facts(barcode)
    if not off_product or not off_product.get("name"):
        await callback.message.edit_text(
            "❓ Товар не найден автоматически.\n\nВведи название товара вручную:"
        )
        await state.set_state(CheckProduct.waiting_manual_name)
        return
    name = off_product["name"]
    brand = off_product.get("brand", "")
    await process_product(callback.message, callback.bot, callback.from_user.id, name, brand, barcode, state)

@router.message(CheckProduct.waiting_manual_name)
async def process_manual_name(message: Message, state: FSMContext):
    name = message.text.strip()
    data = await state.get_data()
    barcode = data.get("barcode", "")
    await state.clear()
    await process_product(message, message.bot, message.from_user.id, name, "", barcode, state, is_message=True)

async def process_product(msg, bot, user_id: int, name: str, brand: str, barcode: str, state, is_message=False):
    product = await get_product_by_name(name, brand)
    status_map = {
        "halal": "✅ ХАЛАЛ",
        "haram": "❌ ХАРАМ",
        "doubtful": "⚠️ СОМНИТЕЛЬНО",
        "unknown": "❓ НЕТ ДАННЫХ"
    }
    text = f"<b>{name}</b>" + (f" — {brand}" if brand else "")
    if product:
        status = product.get("status", "unknown")
        result_text = f"{text}\n\nСтатус: <b>{status_map.get(status, '❓ НЕТ ДАННЫХ')}</b>"
        if is_message:
            await msg.answer(result_text, parse_mode="HTML", reply_markup=main_menu())
        else:
            await msg.edit_text(result_text, parse_mode="HTML")
        await save_history(user_id, barcode, name, brand, status)
    else:
        result_text = f"{text}\n\n❓ Статус: НЕТ ДАННЫХ\n\nЗапрос отправлен администратору — ожидайте ответа."
        if is_message:
            await msg.answer(result_text, parse_mode="HTML", reply_markup=main_menu())
        else:
            await msg.edit_text(result_text, parse_mode="HTML")
        await save_history(user_id, barcode, name, brand, "unknown")
        await bot.send_message(
            ADMIN_ID,
            f"🔔 Новый товар без статуса!\n\n"
            f"<b>{name}</b>" + (f" — {brand}" if brand else "") +
            f"\nШтрихкод: <code>{barcode}</code>\n"
            f"Пользователь: {user_id}\n\n"
            f"Выбери статус:",
            parse_mode="HTML",
            reply_markup=admin_keyboard(name, brand, user_id)
        )

@router.callback_query(F.data.startswith("setstatus:"))
async def set_status_from_admin(callback: CallbackQuery):
    parts = callback.data.split(":")
    status = parts[1]
    user_id = int(parts[2])
    name = parts[3].replace("_", " ")
    brand = parts[4].replace("_", " ") if len(parts) > 4 else ""
    await add_product(name, brand, status)
    status_map = {
        "halal": "✅ ХАЛАЛ",
        "haram": "❌ ХАРАМ",
        "doubtful": "⚠️ СОМНИТЕЛЬНО"
    }
    await callback.message.edit_text(
        f"✅ Статус установлен!\n\n<b>{name}</b>" + (f" — {brand}" if brand else "") +
        f"\nСтатус: <b>{status_map.get(status)}</b>",
        parse_mode="HTML"
    )
    await callback.bot.send_message(
        user_id,
        f"✅ Ответ на ваш запрос:\n\n<b>{name}</b>" + (f" — {brand}" if brand else "") +
        f"\n\nСтатус: <b>{status_map.get(status)}</b>",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.", reply_markup=main_menu())

@router.callback_query(F.data == "manual_input")
async def back_to_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckProduct.waiting_barcode)
    await callback.message.edit_text("Введи штрихкод вручную:")

@router.message(F.text == "📋 История проверок")
async def history_button(message: Message):
    history = await get_user_history(message.from_user.id)
    if not history:
        await message.answer("📭 История проверок пуста.")
        return
    text = "📋 <b>Последние проверки:</b>\n\n"
    status_map = {"halal": "✅", "haram": "❌", "doubtful": "⚠️", "unknown": "❓"}
    for h in history:
        emoji = status_map.get(h["status"], "❓")
        text += f"{emoji} <b>{h['product_name']}</b>" + (f" — {h.get('brand', '')}" if h.get('brand') else "") + "\n"
        text += f"    {h['barcode']} · {h['checked_at'].strftime('%d.%m %H:%M')}\n\n"
    await message.answer(text, parse_mode="HTML")

@router.message(Command("history"))
async def show_history(message: Message):
    history = await get_user_history(message.from_user.id)
    if not history:
        await message.answer("📭 История проверок пуста.")
        return
    text = "📋 <b>Последние проверки:</b>\n\n"
    status_map = {"halal": "✅", "haram": "❌", "doubtful": "⚠️", "unknown": "❓"}
    for h in history:
        emoji = status_map.get(h["status"], "❓")
        text += f"{emoji} <b>{h['product_name']}</b>" + (f" — {h.get('brand', '')}" if h.get('brand') else "") + "\n"
        text += f"    {h['barcode']} · {h['checked_at'].strftime('%d.%m %H:%M')}\n\n"
    await message.answer(text, parse_mode="HTML")