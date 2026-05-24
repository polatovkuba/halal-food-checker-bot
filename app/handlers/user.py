from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.keyboards.buttons import main_menu, confirm_barcode, confirm_product
from app.database.db import get_product, save_history, search_open_food_facts, get_user_history
import io

try:
    from PIL import Image
    from pyzbar.pyzbar import decode
    BARCODE_ENABLED = True
except ImportError:
    BARCODE_ENABLED = False

router = Router()

class CheckProduct(StatesGroup):
    waiting_barcode = State()
    waiting_photo = State()

@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🕌 Assalamu Alaikum!\n\nДобро пожаловать в Halal Food Checker!\n\nОтправь штрихкод товара — узнаем халяль он или нет.",
        reply_markup=main_menu()
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
        await message.answer("❌ Распознавание штрихкода недоступно на сервере. Введи вручную.", reply_markup=main_menu())
        return
    await state.clear()
    photo: PhotoSize = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    image = Image.open(io.BytesIO(file_bytes.read()))
    barcodes = decode(image)
    if not barcodes:
        await message.answer("❌ Штрихкод не найден на фото. Попробуй ещё раз или введи вручную.", reply_markup=main_menu())
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
    await callback.message.edit_text("🔍 Ищем товар...")
    product = await get_product(barcode)
    if not product:
        product = await search_open_food_facts(barcode)
    if product:
        await state.update_data(product=product, barcode=barcode)
        await callback.message.edit_text(
            f"Нашли товар:\n<b>{product['name']}</b>\n{product.get('brand', '')}",
            reply_markup=confirm_product(barcode),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text("❓ Товар не найден в базе.\nСтатус: <b>Нет данных</b>", parse_mode="HTML")

@router.callback_query(F.data.startswith("product_"))
async def show_status(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product = data.get("product", {})
    status = product.get("status", "unknown")
    status_map = {
        "halal": "✅ ХАЛАЛ",
        "haram": "❌ ХАРАМ",
        "doubtful": "⚠️ СОМНИТЕЛЬНО",
        "unknown": "❓ НЕТ ДАННЫХ"
    }
    await callback.message.edit_text(
        f"<b>{product.get('name', 'Товар')}</b>\n\nСтатус: <b>{status_map.get(status, '❓ НЕТ ДАННЫХ')}</b>",
        parse_mode="HTML"
    )
    await save_history(callback.from_user.id, data.get("barcode"), product.get("name"), status)

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
        text += f"{emoji} <b>{h['product_name']}</b>\n"
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
        text += f"{emoji} <b>{h['product_name']}</b>\n"
        text += f"    {h['barcode']} · {h['checked_at'].strftime('%d.%m %H:%M')}\n\n"
    await message.answer(text, parse_mode="HTML")