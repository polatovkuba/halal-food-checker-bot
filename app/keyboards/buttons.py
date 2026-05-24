from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 Фото штрихкода")],
            [KeyboardButton(text="⌨️ Ввести вручную")],
            [KeyboardButton(text="📋 История проверок")],
        ],
        resize_keyboard=True
    )
    return keyboard

def confirm_barcode(barcode: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, правильно", callback_data=f"confirm_{barcode}")],
        [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="manual_input")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])
    return keyboard

def confirm_product(barcode: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, это мой товар", callback_data=f"product_{barcode}")],
        [InlineKeyboardButton(text="❌ Нет, не мой", callback_data="cancel")],
    ])
    return keyboard