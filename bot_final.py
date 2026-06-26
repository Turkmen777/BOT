import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from flask import Flask
import threading
import time
import re
import random
import string

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ King Kassa Bot работает 24/7!"

@app.route('/ping')
def ping():
    return "🏓 Pong"

def run_flask():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ========== НАСТРОЙКИ БОТА ==========
BOT_TOKEN = "8732092975:AAE4OMg6eAwFaKtkVa4aO3yE_LQC9SyJZuw"  # ← ЗАМЕНИТЕ НА СВОЙ ТОКЕН!
GROUP_CHAT_ID = -1005235064939  # ← ЗАМЕНИТЕ НА ID ВАШЕЙ ГРУППЫ!
ADMIN_GROUP_ID = -1005235064939  # ← ЗАМЕНИТЕ НА ID ГРУППЫ ДЛЯ ПАРОЛЕЙ!
SUPPORT_USERNAME = "@king_kassa"  # ← ЗАМЕНИТЕ НА ВАШ ЮЗЕРНЕЙМ!

# ID администраторов (замените на свой)
ADMIN_IDS = [8825795410]  # ← Ваш Telegram ID

# Состояния
(ASK_CLIENT, REG_PHONE, REG_PARIKARA_ID, LOGIN_PHONE, LOGIN_PASSWORD,
 PHONE_INPUT, AMOUNT_INPUT, WITHDRAW_PHONE_INPUT, 
 WITHDRAW_AMOUNT_INPUT, WITHDRAW_RECEIPT_INPUT) = range(10)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище
user_data = {}
applications = {}
app_counter = 1000
registered_users = {}  # Подтверждённые пользователи
pending_users = {}     # Ожидают подтверждения

# ========== ФУНКЦИИ ==========
def validate_parikara_id(text):
    return re.match(r'^\d+$', text) is not None

def validate_amount(text):
    if re.match(r'^\d+$', text):
        amount = int(text)
        if amount >= 30:
            return True
    return False

def validate_phone(text):
    clean_text = re.sub(r'[\s\-\(\)]', '', text)
    if re.match(r'^\+993\d{8}$', clean_text):
        return True
    elif re.match(r'^993\d{8}$', clean_text):
        return True
    elif re.match(r'^\d{8}$', clean_text):
        return True
    return False

def format_phone(text):
    clean_text = re.sub(r'[\s\-\(\)]', '', text)
    if re.match(r'^\d{8}$', clean_text):
        return f"+993 {clean_text[:2]} {clean_text[2:5]} {clean_text[5:]}"
    elif re.match(r'^993\d{8}$', clean_text):
        return f"+{clean_text[:3]} {clean_text[3:5]} {clean_text[5:8]} {clean_text[8:]}"
    elif re.match(r'^\+993\d{8}$', clean_text):
        return f"+993 {clean_text[4:6]} {clean_text[6:9]} {clean_text[9:]}"
    return text

def generate_password():
    return ''.join(random.choices(string.digits, k=6))

def reset_user_data(user_id):
    if user_id in user_data:
        del user_data[user_id]

def is_registered(user_id):
    return user_id in registered_users

# ========== START ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    context.user_data.clear()
    
    if is_registered(user_id):
        return await show_main_menu(update, context)
    
    if user_id in pending_users:
        await update.message.reply_text(
            f"⏳ Вы уже зарегистрировались.\n"
            f"Пароль проверяется администратором.\n"
            f"Для связи: {SUPPORT_USERNAME}\n\n"
            f"⚠️ Если вы уже получили пароль, введите /giris"
        )
        return ConversationHandler.END
    
    keyboard = [
        [KeyboardButton("✅ Да, я клиент")],
        [KeyboardButton("❌ Нет, новая регистрация")]
    ]
    
    await update.message.reply_text(
        "Вы клиент King Kassa? 🤔",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return ASK_CLIENT

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    keyboard = [
        [KeyboardButton("💰 Пополнить счет")],
        [KeyboardButton("💸 Вывести деньги")],
        [KeyboardButton("🆘 Помощь")]
    ]
    
    welcome_text = (
        f"Добро пожаловать, {user.first_name}! 🤖\n\n"
        "Добро пожаловать в King Kassa бот.\n"
        "Для пополнения или вывода средств используйте кнопки ниже."
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ConversationHandler.END

# ========== ОТВЕТ НА ВОПРОС ==========
async def handle_client_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "✅ Да, я клиент":
        await update.message.reply_text(
            "📝 <b>ВХОД</b>\n\n"
            "Введите ваш номер телефона:\n"
            "(Пример: +99365123456 или 65123456)",
            parse_mode='HTML'
        )
        return LOGIN_PHONE
    
    elif text == "❌ Нет, новая регистрация":
        await update.message.reply_text(
            "📝 <b>НОВАЯ РЕГИСТРАЦИЯ</b>\n\n"
            "Введите ваш номер телефона:\n"
            "(Пример: +99365123456 или 65123456)",
            parse_mode='HTML'
        )
        return REG_PHONE
    
    else:
        await update.message.reply_text("Используйте кнопки!")
        return ASK_CLIENT

# ========== ВХОД ==========
async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_phone(text):
        phone = format_phone(text)
        context.user_data['login_phone'] = phone
        context.user_data['login_attempts'] = 0
        
        await update.message.reply_text(
            f"✅ Номер телефона принят\n\n"
            "🔑 Теперь введите ваш пароль:"
        )
        return LOGIN_PASSWORD
    else:
        await update.message.reply_text(
            "❌ Неверный формат!\n"
            "Правильный формат: +99365123456 или 65123456\n"
            "Попробуйте снова:"
        )
        return LOGIN_PHONE

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    if 'login_attempts' not in context.user_data:
        context.user_data['login_attempts'] = 0
    context.user_data['login_attempts'] += 1
    
    if 'login_phone' not in context.user_data:
        await update.message.reply_text("❌ Начните заново с /start.")
        return ConversationHandler.END
    
    login_phone = context.user_data['login_phone']
    
    found_user = None
    for uid, data in registered_users.items():
        if data['phone'] == login_phone:
            found_user = data
            break
    
    if found_user and found_user['password'] == password:
        context.user_data.clear()
        if user_id not in registered_users:
            registered_users[user_id] = found_user
        
        await update.message.reply_text("✅ Вход выполнен успешно!")
        return await show_main_menu(update, context)
    else:
        attempts = context.user_data['login_attempts']
        
        if attempts >= 5:
            await update.message.reply_text(
                f"❌ 5 неверных попыток ввода пароля!\n"
                f"Ваш аккаунт временно заблокирован.\n"
                f"Связь: {SUPPORT_USERNAME}"
            )
            context.user_data.clear()
            return ConversationHandler.END
        else:
            remaining = 5 - attempts
            await update.message.reply_text(
                f"❌ Неверный пароль! Осталось {remaining} попыток.\n"
                f"🔑 Введите пароль снова:"
            )
            return LOGIN_PASSWORD

# ========== РЕГИСТРАЦИЯ: ТЕЛЕФОН ==========
async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_phone(text):
        phone = format_phone(text)
        user_data[user_id] = {'phone': phone}
        
        await update.message.reply_text(
            f"✅ Номер телефона принят: {phone}\n\n"
            "📝 Теперь введите ваш Parikara ID:\n"
            "(Только цифры)"
        )
        return REG_PARIKARA_ID
    else:
        await update.message.reply_text(
            "❌ Неверный формат!\n"
            "Правильный формат: +99365123456 или 65123456\n"
            "Попробуйте снова:"
        )
        return REG_PHONE

# ========== РЕГИСТРАЦИЯ: PARIKARA ID ==========
async def reg_parikara_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id not in user_data or 'phone' not in user_data[user_id]:
        await update.message.reply_text("❌ Начните заново с /start.")
        return ConversationHandler.END
    
    if validate_parikara_id(text):
        parikara_id = text
        phone = user_data[user_id]['phone']
        password = generate_password()
        user = update.effective_user
        username = user.username or "нет"
        
        pending_users[user_id] = {
            'user_id': user_id,
            'username': username,
            'first_name': user.first_name,
            'phone': phone,
            'parikara_id': parikara_id,
            'password': password,
            'registered_date': datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        admin_message = (
            f"🆕 <b>НОВАЯ РЕГИСТРАЦИЯ</b>\n\n"
            f"👤 Пользователь: @{username}\n"
            f"📝 Имя: {user.first_name}\n"
            f"📞 Телефон: {phone}\n"
            f"🆔 Parikara ID: {parikara_id}\n"
            f"🔑 ПАРОЛЬ: <code>{password}</code>\n"
            f"⏰ Время: {pending_users[user_id]['registered_date']}\n\n"
            f"✅ Для подтверждения:\n"
            f"/confirm {phone}\n\n"
            f"⚠️ <b>ПАРОЛЬ ВЫДАВАЙТЕ ТОЛЬКО КЛИЕНТУ!</b>"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=admin_message,
            parse_mode='HTML'
        )
        
        await update.message.reply_text(
            f"✅ <b>РЕГИСТРАЦИЯ УСПЕШНА</b>\n\n"
            f"📞 Ваш логин: {phone}\n\n"
            f"🔐 <b>ПАРОЛЬ У АДМИНИСТРАТОРА</b>\n"
            f"Для получения пароля свяжитесь с администратором:\n"
            f"{SUPPORT_USERNAME}\n\n"
            f"⚠️ <b>После получения пароля введите /start для входа.</b>",
            parse_mode='HTML'
        )
        
        del user_data[user_id]
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Ошибка! Введите только цифры.\n"
            "Введите Parikara ID снова:"
        )
        return REG_PARIKARA_ID

# ========== АДМИН: ПОДТВЕРЖДЕНИЕ РЕГИСТРАЦИИ ==========
async def confirm_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return
    
    try:
        phone = ' '.join(context.args)
    except:
        await update.message.reply_text("❌ Формат: /confirm +99365123456")
        return
    
    phone = phone.strip()
    
    found_user_id = None
    found_user_data = None
    for uid, data in pending_users.items():
        if data['phone'] == phone:
            found_user_id = uid
            found_user_data = data
            break
    
    if found_user_id:
        registered_users[found_user_id] = found_user_data
        del pending_users[found_user_id]
        
        await update.message.reply_text(
            f"✅ {phone} подтвержден!\n"
            f"Теперь клиент может войти.\n"
            f"Пароль: {found_user_data['password']}"
        )
        
        try:
            await context.bot.send_message(
                chat_id=found_user_id,
                text=(
                    f"✅ <b>РЕГИСТРАЦИЯ ПОДТВЕРЖДЕНА!</b>\n\n"
                    f"📞 Ваш логин: {phone}\n"
                    f"🔑 Ваш пароль: <code>{found_user_data['password']}</code>\n\n"
                    f"Теперь введите /start для входа.",
                    parse_mode='HTML'
                )
            )
        except:
            pass
    else:
        await update.message.reply_text(f"❌ {phone} не найден в регистрациях")

# ========== КОМАНДА ДЛЯ ВХОДА ==========
async def giris_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 <b>ВХОД</b>\n\n"
        "Введите ваш номер телефона:",
        parse_mode='HTML'
    )
    return LOGIN_PHONE

# ========== КНОПКА ПОМОЩИ ==========
async def support_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
        return
    
    support_text = (
        f"🆘 <b>СЛУЖБА ПОДДЕРЖКИ</b>\n\n"
        f"Если возникли проблемы или вопросы,\n"
        f"обратитесь по контакту ниже:\n\n"
        f"📞 <b>{SUPPORT_USERNAME}</b>\n\n"
        f"Режим работы: 24/7"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Написать", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")]
    ])
    
    await update.message.reply_text(
        support_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

# ========== ПОПОЛНЕНИЕ СЧЁТА ==========
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
        return ConversationHandler.END
    
    reset_user_data(user_id)
    user_data[user_id] = {'action': 'deposit'}
    await update.message.reply_text("🔑 Введите ваш Parikara ID:\n(Только цифры)")
    return PHONE_INPUT

async def deposit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'deposit':
        await update.message.reply_text("❌ Начните заново с /start.")
        return ConversationHandler.END
    
    if validate_parikara_id(text):
        user_data[user_id]['parikara_id'] = text
        await update.message.reply_text(
            f"✅ ID принят: {text}\n\n"
            "💵 Введите сумму пополнения:\n"
            "(Минимум 30 TMT, только цифры)"
        )
        return AMOUNT_INPUT
    else:
        await update.message.reply_text("❌ Ошибка! Введите только цифры.\nParikara ID:")
        return PHONE_INPUT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global app_counter
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'deposit':
        await update.message.reply_text("❌ Начните заново с /start.")
        return ConversationHandler.END
    
    if validate_amount(text):
        amount = text
        user_data[user_id]['amount'] = amount
        app_id = app_counter
        app_counter += 1
        
        reg_data = registered_users[user_id]
        user = update.effective_user
        username = user.username or "нет"
        
        applications[app_id] = {
            'id': app_id,
            'user_id': user_id,
            'username': username,
            'first_name': user.first_name,
            'type': 'deposit',
            'parikara_id': user_data[user_id]['parikara_id'],
            'amount': amount,
            'phone': reg_data['phone'],
            'time': datetime.now().strftime("%H:%M %d.%m.%Y"),
            'status': 'waiting_phone'
        }
        
        group_message = (
            f"🆕 <b>НОВАЯ ЗАЯВКА #{app_id}</b>\n\n"
            f"👤 Клиент: @{username}\n"
            f"📞 Телефон: {reg_data['phone']}\n"
            f"🆔 Parikara ID: {user_data[user_id]['parikara_id']}\n"
            f"💰 Сумма: {amount} TMT\n"
            f"⏰ Время: {applications[app_id]['time']}\n\n"
            f"<b>Для отправки реквизитов:</b>\n"
            f"(Ответьте на это сообщение 8 цифрами, пример: 65656565)"
        )
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=group_message,
            parse_mode='HTML'
        )
        
        await update.message.reply_text(
            f"✅ Заявка #{app_id} принята!\n\n"
            "📞 Ожидайте реквизиты...\n\n"
            f"🆘 Помощь: {SUPPORT_USERNAME}"
        )
        
        reset_user_data(user_id)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Неверная сумма! Минимум 30 TMT.\nВведите сумму снова:")
        return AMOUNT_INPUT

# ========== ВЫВОД СРЕДСТВ ==========
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
        return ConversationHandler.END
    
    reset_user_data(user_id)
    user_data[user_id] = {'action': 'withdraw'}
    await update.message.reply_text("🔑 Введите ваш Parikara ID:\n(Только цифры)")
    return WITHDRAW_PHONE_INPUT

async def withdraw_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'withdraw':
        await update.message.reply_text("❌ Начните заново с /start.")
        return ConversationHandler.END
    
    if validate_parikara_id(text):
        user_data[user_id]['parikara_id'] = text
        await update.message.reply_text(
            f"✅ ID принят: {text}\n\n"
            "💵 Введите сумму для вывода:\n"
            "(Только цифры)"
        )
        return WITHDRAW_AMOUNT_INPUT
    else:
        await update.message.reply_text("❌ Ошибка! Введите только цифры.\nParikara ID:")
        return WITHDRAW_PHONE_INPUT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'withdraw':
        await update.message.reply_text("❌ Начните заново с /start.")
        return ConversationHandler.END
    
    if re.match(r'^\d+$', text):
        amount = text
        user_data[user_id]['amount'] = amount
        await update.message.reply_text(
            f"✅ Сумма принята: {amount} TMT\n\n"
            "📞 Введите ваш номер телефона:\n"
            "(8 цифр, пример: 65123456)"
        )
        return WITHDRAW_RECEIPT_INPUT
    else:
        await update.message.reply_text("❌ Ошибка! Введите только цифры.\nСумма:")
        return WITHDRAW_AMOUNT_INPUT

async def withdraw_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global app_counter
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'withdraw':
        await update.message.reply_text("❌ Начните заново с /start.")
        return ConversationHandler.END
    
    if validate_phone(text):
        phone = format_phone(text)
        user = update.effective_user
        username = user.username or "нет"
        app_id = app_counter
        app_counter += 1
        
        reg_data = registered_users[user_id]
        
        applications[app_id] = {
            'id': app_id,
            'user_id': user_id,
            'username': username,
            'first_name': user.first_name,
            'type': 'withdraw',
            'parikara_id': user_data[user_id]['parikara_id'],
            'amount': user_data[user_id]['amount'],
            'phone': phone,
            'user_phone': reg_data['phone'],
            'time': datetime.now().strftime("%H:%M %d.%m.%Y"),
            'status': 'waiting_confirm'
        }
        
        group_message = (
            f"🔴 <b>НОВАЯ ЗАЯВКА: ВЫВОД #{app_id}</b>\n\n"
            f"👤 Клиент: @{username}\n"
            f"📞 Телефон: {reg_data['phone']}\n"
            f"🆔 Parikara ID: {user_data[user_id]['parikara_id']}\n"
            f"💰 Сумма: {user_data[user_id]['amount']} TMT\n"
            f"📞 Номер клиента: {phone}\n"
            f"⏰ Время: {applications[app_id]['time']}\n\n"
            f"<b>После перевода денег:</b>"
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_withdraw_{app_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_withdraw_{app_id}")
            ]
        ])
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=group_message,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        
        await update.message.reply_text(
            f"✅ Заявка #{app_id} принята!\n\n"
            "💸 Заявка на вывод обрабатывается.\n\n"
            f"🆘 Помощь: {SUPPORT_USERNAME}"
        )
        
        reset_user_data(user_id)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Неверный номер телефона!\n"
            "Правильный формат: 65123456 (8 цифр)\n"
            "Попробуйте снова:"
        )
        return WITHDRAW_RECEIPT_INPUT

# ========== ОБРАБОТКА СООБЩЕНИЙ В ГРУППЕ ==========
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_CHAT_ID:
        return
    
    text = update.message.text.strip()
    
    if re.match(r'^\d{8}$', text):
        if update.message.reply_to_message:
            original_text = update.message.reply_to_message.text or ""
            match = re.search(r'#(\d+)', original_text)
            if match:
                app_id = int(match.group(1))
                if app_id in applications:
                    app = applications[app_id]
                    
                    if app['type'] == 'deposit':
                        phone = format_phone(text)
                        
                        await context.bot.send_message(
                            chat_id=app['user_id'],
                            text=(
                                f"📞 <b>РЕКВИЗИТЫ #{app_id}</b>\n\n"
                                f"💳 Номер: <code>{phone}</code>\n"
                                f"💰 Сумма: {app['amount']} TMT\n\n"
                                f"После оплаты отправьте скриншот!\n\n"
                                f"🆘 Помощь: {SUPPORT_USERNAME}"
                            ),
                            parse_mode='HTML'
                        )
                        
                        await update.message.reply_text(
                            f"✔ Реквизиты отправлены #{app_id}\n\n"
                            f"👤 Клиент: @{app['username']}\n"
                            f"📞 Телефон: {app['phone']}\n"
                            f"📞 Номер: {phone}\n"
                            f"💰 Сумма: {app['amount']} TMT\n\n"
                            f"Ожидаем скриншот..."
                        )
                        
                        app['status'] = 'waiting_screenshot'
                        app['sent_phone'] = phone
                        return

# ========== ОБРАБОТКА СКРИНШОТОВ ==========
async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        user = update.effective_user
        
        if not is_registered(user.id):
            await update.message.reply_text("❌ Сначала зарегистрируйтесь! /start")
            return
        
        user_app = None
        for app_id, app in applications.items():
            if app['user_id'] == user.id and app['status'] == 'waiting_screenshot':
                user_app = app
                break
        
        if user_app:
            app_id = user_app['id']
            applications[app_id]['screenshot_id'] = file_id
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{app_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{app_id}")
                ]
            ])
            
            caption = (
                f"🖼 <b>Скриншот #{app_id}</b>\n\n"
                f"👤 Клиент: @{user_app['username']}\n"
                f"📞 Телефон: {user_app['phone']}\n"
                f"💰 Сумма: {user_app['amount']} TMT"
            )
            
            await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=file_id,
                caption=caption,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            
            await update.message.reply_text("✅ Скриншот получен! Ожидайте подтверждения.")
        else:
            await update.message.reply_text("❌ Активная заявка не найдена")
    else:
        await update.message.reply_text("❌ Отправьте фото!")

# ========== ОБРАБОТКА КНОПОК ==========
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    action = data[0]
    
    if action == 'approve':
        app_id = int(data[1])
        
        if app_id not in applications:
            await query.edit_message_caption("❌ Заявка не найдена")
            return
        
        app = applications[app_id]
        app['status'] = 'completed'
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"✅ <b>ПЛАТЕЖ ПОДТВЕРЖДЕН #{app_id}</b>\n\n"
                f"💰 Сумма: {app['amount']} TMT\n\n"
                f"🆘 Помощь: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n✅ <b>ПОДТВЕРЖДЕН #{app_id}</b>",
            parse_mode='HTML'
        )
    
    elif action == 'reject' and len(data) == 2:
        app_id = int(data[1])
        
        if app_id not in applications:
            await query.edit_message_caption("❌ Заявка не найдена")
            return
        
        app = applications[app_id]
        app['status'] = 'rejected'
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"❌ <b>ПЛАТЕЖ ОТКЛОНЕН #{app_id}</b>\n\n"
                f"💰 Сумма: {app['amount']} TMT\n\n"
                f"Связь: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n❌ <b>ОТКЛОНЕН #{app_id}</b>",
            parse_mode='HTML'
        )
    
    elif action == 'confirm' and data[1] == 'withdraw':
        app_id = int(data[2])
        
        if app_id not in applications:
            await query.edit_message_text("❌ Заявка не найдена")
            return
        
        app = applications[app_id]
        app['status'] = 'completed'
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"✅ <b>ДЕНЬГИ ВЫВЕДЕНЫ #{app_id}</b>\n\n"
                f"💰 Сумма: {app['amount']} TMT\n\n"
                f"Спасибо за использование! 🤝\n\n"
                f"🆘 Помощь: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_text(
            text=query.message.text + f"\n\n✅ <b>ПОДТВЕРЖДЕН #{app_id}</b>",
            parse_mode='HTML'
        )
    
    elif action == 'reject' and data[1] == 'withdraw':
        app_id = int(data[2])
        
        if app_id not in applications:
            await query.edit_message_text("❌ Заявка не найдена")
            return
        
        app = applications[app_id]
        app['status'] = 'rejected'
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"❌ <b>ВЫВОД ОТКЛОНЕН #{app_id}</b>\n\n"
                f"💰 Сумма: {app['amount']} TMT\n\n"
                f"Связь: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_text(
            text=query.message.text + f"\n\n❌ <b>ОТКЛОНЕН #{app_id}</b>",
            parse_mode='HTML'
        )

# ========== ОТМЕНА ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_user_data(user_id)
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено.\nДля начала введите /start.")
    return ConversationHandler.END

# ========== ЗАПУСК ==========
def main():
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()
    time.sleep(2)
    
    print("=" * 60)
    print("👑 KING KASSA BOT - РУССКАЯ ВЕРСИЯ")
    print("📱 Бот запущен! 24/7")
    print("🔐 Регистрация: Пароль только админу")
    print("👤 Админ: /confirm +99365123456")
    print("=" * 60)
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_CLIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_answer)],
            REG_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_phone)],
            REG_PARIKARA_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_parikara_id)],
            LOGIN_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
            PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_phone)],
            AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            WITHDRAW_PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone)],
            WITHDRAW_AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_RECEIPT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_receipt)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("confirm", confirm_user))
    application.add_handler(CommandHandler("giris", giris_command))
    application.add_handler(MessageHandler(filters.Regex("^💰 Пополнить счет$"), deposit_start))
    application.add_handler(MessageHandler(filters.Regex("^💸 Вывести деньги$"), withdraw_start))
    application.add_handler(MessageHandler(filters.Regex("^🆘 Помощь$"), support_button))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=GROUP_CHAT_ID) & ~filters.COMMAND,
        handle_group_message
    ))
    
    print("✅ Бот готов к работе!")
    print("👉 Откройте бота и введите /start")
    print("=" * 60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
