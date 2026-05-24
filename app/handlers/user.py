from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.keyboards.buttons import main_menu, confirm_barcode, confirm_product
from app.database.db import get_product_by_name, save_history, search_open_food_facts, get_user_history
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
    await state.update_data(name=name, brand=brand)
    await check_and_respond(callback, state, name, brand, barcode)

@router.message(CheckProduct.waiting_manual_name)
async def process_manual_name(message: Message, state: FSMContext):
    name = message.text.strip()
    data = await state.get_data()
    barcode = data.get("barcode", "")
    brand = ""
    await state.update_data(name=name, brand=brand)
    await check_and_respond_message(message, state, name, brand, barcode)

async def check_and_respond(callback: CallbackQuery, state: FSMContext, name: str, brand: str, barcode: str):
    product = await get_product_by_name(name, brand)
    status_map = {
        "halal": "✅ ХАЛАЛ",
        "haram": "❌ ХАРАМ",
        "doubtful": "⚠️ СОМНИТЕЛЬНО",
        "unknown": "❓ НЕТ ДАННЫХ"
    }
    if product:
        status = product.get("status", "unknown")
        await callback.message.edit_text(
            f"<b>{name}</b>" + (f" — {brand}" if brand else "") +
            f"\n\nСтатус: <b>{status_map.get(status, '❓ НЕТ ДАННЫХ')}</b>",
            parse_mode="HTML"
        )
        await save_history(callback.from_user.id, barcode, name, brand, status)
    else:
        await callback.message.edit_text(
            f"<b>{name}</b>" + (f" — {brand}" if brand else "") +
            f"\n\n❓ Статус: НЕТ ДАННЫХ\n\nМы отправили запрос администратору.",
            parse_mode="HTML"
        )
        await save_history(callback.from_user.id, barcode, name, brand, "unknown")
        await callback.bot.send_message(
            ADMIN_ID,
            f"🔔 Новый товар без статуса!\n\n"
            f"<b>{name}</b>" + (f" — {brand}" if brand else "") +
            f"\nШтрихкод: <code>{barcode}</code>\n\n"
            f"Добавь через /admin",
            parse_mode="HTML"
        )

async def check_and_respond_message(message: Message, state: FSMContext, name: str, brand: str, barcode: str):
    await state.clear()
    product = await get_product_by_name(name, brand)
    status_map = {
        "halal": "✅ ХАЛАЛ",
        "haram": "❌ ХАРАМ",
        "doubtful": "⚠️ СОМНИТЕЛЬНО",
        "unknown": "❓ НЕТ ДАННЫХ"
    }
    if product:
        status = product.get("status", "unknown")
        await message.answer(
            f"<b>{name}</b>" + (f" — {brand}" if brand else "") +
            f"\n\nСтатус: <b>{status_map.get(status, '❓ НЕТ ДАННЫХ')}</b>",
            parse_mode="HTML"
        )
        await save_history(message.from_user.id, barcode, name, brand, status)
    else:
        await message.answer(
            f"<b>{name}</b>" + (f" — {brand}" if brand else "") +
            f"\n\n❓ Статус: НЕТ ДАННЫХ\n\nМы отправили запрос администратору.",
            parse_mode="HTML"
        )
        await save_history(message.from_user.id, barcode, name, brand, "unknown")
        await message.bot.send_message(
            ADMIN_ID,
            f"🔔 Новый товар без статуса!\n\n"
            f"<b>{name}</b>\nШтрихкод: <code>{barcode}</code>\n\n"
            f"Добавь через /admin",
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