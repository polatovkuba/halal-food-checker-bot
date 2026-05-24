from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.database.db import add_product, get_all_products
import os

router = Router()
ADMIN_IDS = [int(os.getenv("ADMIN_ID", "0"))]

class AddProduct(StatesGroup):
    name = State()
    brand = State()
    status = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет доступа.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")],
        [InlineKeyboardButton(text="📋 Список товаров", callback_data="admin_list")],
    ])
    await message.answer("🔧 Админ-панель:", reply_markup=keyboard)

@router.callback_query(F.data == "admin_add")
async def admin_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AddProduct.name)
    await callback.message.edit_text("Введи название товара:")

@router.message(AddProduct.name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip().lower())
    await state.set_state(AddProduct.brand)
    await message.answer("Введи бренд товара:")

@router.message(AddProduct.brand)
async def add_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text.strip().lower())
    await state.set_state(AddProduct.status)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Халал", callback_data="status_halal")],
        [InlineKeyboardButton(text="❌ Харам", callback_data="status_haram")],
        [InlineKeyboardButton(text="⚠️ Сомнительно", callback_data="status_doubtful")],
    ])
    await message.answer("Выбери статус:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("status_"))
async def add_status(callback: CallbackQuery, state: FSMContext):
    status = callback.data.replace("status_", "")
    data = await state.get_data()
    await state.clear()
    await add_product(data["name"], data["brand"], status)
    await callback.message.edit_text(
        f"✅ Товар добавлен!\n\n<b>{data['name']}</b> — {data['brand']}\nСтатус: {status}",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_list")
async def admin_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    products = await get_all_products()
    if not products:
        await callback.message.edit_text("База пуста.")
        return
    text = "📋 Товары в базе:\n\n"
    status_map = {"halal": "✅", "haram": "❌", "doubtful": "⚠️"}
    for p in products[:20]:
        emoji = status_map.get(p["status"], "❓")
        text += f"{emoji} <b>{p['name']}</b> — {p['brand']}\n"
    await callback.message.edit_text(text, parse_mode="HTML")