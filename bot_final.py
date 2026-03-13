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
    return "✅ Astra Kassa Bot işleýär 24/7!"

@app.route('/ping')
def ping():
    return "🏓 Pong"

def run_flask():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ========== НАСТРОЙКИ БОТА ==========
BOT_TOKEN = "8741918027:AAEqpPPZBDO54UZcmxyJb_U4gfuVqc97j5w"
GROUP_CHAT_ID = -1003759188641  # Группа для заявок
ADMIN_GROUP_ID = -1005200800718  # Группа для паролей (можно ту же или отдельную)
SUPPORT_USERNAME = "@astra_kassa"

# Состояния для разговоров
(ASK_CLIENT, REG_PHONE, REG_PARIKARA_ID, LOGIN_PHONE, LOGIN_PASSWORD,
 PHONE_INPUT, AMOUNT_INPUT, WITHDRAW_PHONE_INPUT, 
 WITHDRAW_AMOUNT_INPUT, WITHDRAW_RECEIPT_INPUT) = range(10)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище данных
user_data = {}
applications = {}
app_counter = 1000
pending_registrations = {}  # Ожидают подтверждения пароля
registered_users = {}  # {user_id: {'phone': '...', 'parikara_id': '...', 'password': '...'}}

# ========== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ==========
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
    """Генерирует пароль из 6 цифр"""
    return ''.join(random.choices(string.digits, k=6))

def reset_user_data(user_id):
    if user_id in user_data:
        del user_data[user_id]

def is_registered(user_id):
    """Проверяет, зарегистрирован ли пользователь"""
    return user_id in registered_users

# ========== КОМАНДА /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    
    # Если пользователь уже зарегистрирован, показываем главное меню
    if is_registered(user_id):
        return await show_main_menu(update, context)
    
    # Спрашиваем, клиент ли он
    keyboard = [
        [KeyboardButton("✅ Hawa, men müşderi")],
        [KeyboardButton("❌ Ýok, täze registrasiýa")]
    ]
    
    await update.message.reply_text(
        "Siz Astra Kassa müşderisimi? 🤔",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return ASK_CLIENT

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню для зарегистрированных"""
    user = update.effective_user
    
    keyboard = [
        [KeyboardButton("💰 Hasaby doldurmak")],
        [KeyboardButton("💸 Pul çykarmak")],
        [KeyboardButton("🆘 Ýardam")]
    ]
    
    welcome_text = (
        f"Hoş geldiňiz, {user.first_name}! 🤖\n\n"
        "Astra Kassa botyna hoş geldiňiz.\n"
        "Hasaby doldurmak ýa-da pul çykarmak üçin aşakdaky düwmeleri ulanyň.\n\n"
        "Näsazlyk ýüze çyksa, '🆘 Ýardam' düwmesine basyň."
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ConversationHandler.END

# ========== ОБРАБОТКА ОТВЕТА НА ВОПРОС О КЛИЕНТЕ ==========
async def handle_client_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ответ на вопрос о клиенте"""
    text = update.message.text
    
    if text == "✅ Hawa, men müşderi":
        # Просим ввести логин и пароль
        await update.message.reply_text(
            "📝 <b>GIRIŞ</b>\n\n"
            "Telefon nomeriňizi ýazyň:\n"
            "(Mysal: +99365123456 ýa-da 65123456)",
            parse_mode='HTML'
        )
        return LOGIN_PHONE
    
    elif text == "❌ Ýok, täze registrasiýa":
        # Начинаем регистрацию
        await update.message.reply_text(
            "📝 <b>TÄZE REGISTRASIÝA</b>\n\n"
            "Telefon nomeriňizi ýazyň:\n"
            "(Mysal: +99365123456 ýa-da 65123456)",
            parse_mode='HTML'
        )
        return REG_PHONE
    
    else:
        await update.message.reply_text("Düwmeleri ulanyň!")
        return ASK_CLIENT

# ========== ВХОД ПО ЛОГИНУ И ПАРОЛЮ ==========
async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение телефона для входа"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_phone(text):
        phone = format_phone(text)
        user_data[user_id] = {'login_phone': phone}
        
        await update.message.reply_text(
            f"✅ Telefon nomeri kabul edildi\n\n"
            "🔑 Indi parolyňyzy ýazyň:"
        )
        return LOGIN_PASSWORD
    else:
        await update.message.reply_text(
            "❌ Ýalňyş format!\n"
            "Dogry format: +99365123456 ýa-da 65123456\n"
            "Täzeden ýazyň:"
        )
        return LOGIN_PHONE

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка пароля"""
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    # Проверяем пароль
    if user_id in registered_users and registered_users[user_id]['password'] == password:
        # Пароль верный
        await update.message.reply_text("✅ Giriş üstünlikli!")
        return await show_main_menu(update, context)
    else:
        # Пароль неверный
        await update.message.reply_text(
            "❌ Ýalňyş parol!\n"
            "Parolyňyzy ýatdan çykaran bolsaňyz, admin bilen habarlaşyň: @astra_kassa"
        )
        return ConversationHandler.END

# ========== РЕГИСТРАЦИЯ: ПОЛУЧЕНИЕ ТЕЛЕФОНА ==========
async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение номера телефона при регистрации"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_phone(text):
        phone = format_phone(text)
        user_data[user_id] = {'phone': phone}
        
        await update.message.reply_text(
            f"✅ Telefon nomeri kabul edildi: {phone}\n\n"
            "📝 Indi Parikara ID-nizi ýazyň:\n"
            "(Diňe sanlar)"
        )
        return REG_PARIKARA_ID
    else:
        await update.message.reply_text(
            "❌ Ýalňyş format!\n"
            "Dogry format: +99365123456 ýa-da 65123456\n"
            "Täzeden ýazyň:"
        )
        return REG_PHONE

# ========== РЕГИСТРАЦИЯ: ПОЛУЧЕНИЕ PARIKARA ID ==========
async def reg_parikara_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение Parikara ID при регистрации"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_parikara_id(text):
        parikara_id = text
        phone = user_data[user_id]['phone']
        password = generate_password()
        user = update.effective_user
        username = user.username or "ýok"
        
        # Сохраняем в ожидающие подтверждения
        pending_registrations[user_id] = {
            'user_id': user_id,
            'username': username,
            'first_name': user.first_name,
            'phone': phone,
            'parikara_id': parikara_id,
            'password': password,
            'registered_date': datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        # Отправляем пароль ТОЛЬКО В ГРУППУ АДМИНУ
        admin_message = (
            f"🆕 <b>TÄZE REGISTRASIÝA</b>\n\n"
            f"👤 Ulanyjy: @{username}\n"
            f"📝 Ady: {user.first_name}\n"
            f"📞 Telefon: {phone}\n"
            f"🆔 Parikara ID: {parikara_id}\n"
            f"🔑 PAROL: <code>{password}</code>\n"
            f"⏰ Wagt: {pending_registrations[user_id]['registered_date']}\n\n"
            f"✅ Paroly müşderä bermek üçin:\n"
            f"@astra_kassa arkaly habarlaşyň"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=admin_message,
            parse_mode='HTML'
        )
        
        # Клиенту отправляем только логин (БЕЗ ПАРОЛЯ!)
        await update.message.reply_text(
            f"✅ <b>REGISTRASIÝA ÜSTÜNLIKLI</b>\n\n"
            f"📞 Siziň loginiňiz: {phone}\n\n"
            f"🔐 <b>PAROLYŇYZ ADMINDA</b>\n"
            f"Parolyňyzy almak üçin admin bilen habarlaşyň:\n"
            f"{SUPPORT_USERNAME}\n\n"
            f"Paroly alanyňyzdan soň, /start basyp giriň.",
            parse_mode='HTML'
        )
        
        # Очищаем временные данные
        del user_data[user_id]
        
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Ýalňyş! Diňe san giriziň.\n"
            "Parikara ID-nizi täzeden ýazyň:"
        )
        return REG_PARIKARA_ID

# ========== АДМИН: ПОДТВЕРЖДЕНИЕ РЕГИСТРАЦИИ ==========
# Эту функцию можно вызвать отдельно, когда вы даёте пароль клиенту
async def confirm_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ подтверждает регистрацию и активирует пользователя"""
    # Это можно сделать через команду /confirm user_id
    # Но пока клиент может зайти по паролю только когда вы его активируете
    pass

# ========== КНОПКА ПОДДЕРЖКИ ==========
async def support_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки поддержки"""
    support_text = (
        f"🆘 <b>ÝARDAM HYZMATY</b>\n\n"
        f"Näsazlyk ýüze çykan ýa-da soraglaryňyz bar bolsa, \n"
        f"aşakdaky kontakt arkaly habarlaşyp bilersiňiz:\n\n"
        f"📞 <b>{SUPPORT_USERNAME}</b>\n\n"
        f"İş wagty: 24/7"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Habar ýazmak", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")]
    ])
    
    await update.message.reply_text(
        support_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

# ========== ПОПОЛНЕНИЕ СЧЁТА (ТОЛЬКО ДЛЯ ЗАРЕГИСТРИРОВАННЫХ) ==========
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Öň registrasiýadan geçmeli! /start basyň.")
        return ConversationHandler.END
    
    reset_user_data(user_id)
    user_data[user_id] = {'action': 'deposit'}
    await update.message.reply_text("🔑 Parikara ID-nizi ýazyň:\n(Diňe sanlar)")
    return PHONE_INPUT

async def deposit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Öň registrasiýadan geçmeli! /start basyň.")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'deposit':
        await update.message.reply_text("❌ Başdan başlamak üçin /start basyň.")
        return ConversationHandler.END
    
    if validate_parikara_id(text):
        user_data[user_id]['parikara_id'] = text
        await update.message.reply_text(
            f"✅ ID kabul edildi: {text}\n\n"
            "💵 Näçe TMT doldurmaly?\n"
            "(Iň az 30 TMT, diňe san)"
        )
        return AMOUNT_INPUT
    else:
        await update.message.reply_text("❌ Ýalňyş! Diňe san giriziň.\nParikara ID-nizi täzeden ýazyň:")
        return PHONE_INPUT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global app_counter
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Öň registrasiýadan geçmeli! /start basyň.")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'deposit':
        await update.message.reply_text("❌ Başdan başlamak üçin /start basyň.")
        return ConversationHandler.END
    
    if validate_amount(text):
        amount = text
        user_data[user_id]['amount'] = amount
        app_id = app_counter
        app_counter += 1
        
        reg_data = registered_users[user_id]
        user = update.effective_user
        username = user.username or "ýok"
        
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
            f"🆕 <b>TÄZE HAÝYŞ #{app_id}</b>\n\n"
            f"👤 Klient: @{username}\n"
            f"📞 Telefon: {reg_data['phone']}\n"
            f"🆔 Parikara ID: {user_data[user_id]['parikara_id']}\n"
            f"💰 Summa: {amount} TMT\n"
            f"⏰ Wagt: {applications[app_id]['time']}\n\n"
            f"<b>Telefon nomerini ugratmak üçin:</b>\n"
            f"(Bu habara jogap edip 8 san ýazyň, mysal: 65656565)"
        )
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=group_message,
            parse_mode='HTML'
        )
        
        await update.message.reply_text(
            f"✅ Haýyşyňyz #{app_id} kabul edildi!\n\n"
            "📞 Rekwizitleri garaşyň...\n\n"
            f"🆘 Kömek gerek bolsa: {SUPPORT_USERNAME}"
        )
        
        reset_user_data(user_id)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Ýalňyş summa! Iň az 30 TMT bolmaly.\nTäzeden ýazyň:")
        return AMOUNT_INPUT

# ========== ВЫВОД СРЕДСТВ (ТОЛЬКО ДЛЯ ЗАРЕГИСТРИРОВАННЫХ) ==========
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Öň registrasiýadan geçmeli! /start basyň.")
        return ConversationHandler.END
    
    reset_user_data(user_id)
    user_data[user_id] = {'action': 'withdraw'}
    await update.message.reply_text("🔑 Parikara ID-nizi ýazyň:\n(Diňe sanlar)")
    return WITHDRAW_PHONE_INPUT

async def withdraw_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Öň registrasiýadan geçmeli! /start basyň.")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'withdraw':
        await update.message.reply_text("❌ Başdan başlamak üçin /start basyň.")
        return ConversationHandler.END
    
    if validate_parikara_id(text):
        user_data[user_id]['parikara_id'] = text
        await update.message.reply_text(
            f"✅ ID kabul edildi: {text}\n\n"
            "💵 Näçe TMT çykarmaly?\n(Diňe san)"
        )
        return WITHDRAW_AMOUNT_INPUT
    else:
        await update.message.reply_text("❌ Ýalňyş! Diňe san giriziň.\nParikara ID-nizi täzeden ýazyň:")
        return WITHDRAW_PHONE_INPUT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Öň registrasiýadan geçmeli! /start basyň.")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'withdraw':
        await update.message.reply_text("❌ Başdan başlamak üçin /start basyň.")
        return ConversationHandler.END
    
    if re.match(r'^\d+$', text):
        amount = text
        user_data[user_id]['amount'] = amount
        await update.message.reply_text(
            f"✅ Summa kabul edildi: {amount} TMT\n\n"
            "📞 Telefon nomeriňizi ýazyň:\n"
            "(8 san, mysal: 65123456)"
        )
        return WITHDRAW_RECEIPT_INPUT
    else:
        await update.message.reply_text("❌ Ýalňyş! Diňe san giriziň.\nTäzeden ýazyň:")
        return WITHDRAW_AMOUNT_INPUT

async def withdraw_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global app_counter
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_registered(user_id):
        await update.message.reply_text("❌ Öň registrasiýadan geçmeli! /start basyň.")
        return ConversationHandler.END
    
    if user_id not in user_data or user_data[user_id].get('action') != 'withdraw':
        await update.message.reply_text("❌ Başdan başlamak üçin /start basyň.")
        return ConversationHandler.END
    
    if validate_phone(text):
        phone = format_phone(text)
        user = update.effective_user
        username = user.username or "ýok"
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
            f"🔴 <b>TÄZE HAÝYŞ: PUL ÇYKARMAK #{app_id}</b>\n\n"
            f"👤 Klient: @{username}\n"
            f"📞 Telefon: {reg_data['phone']}\n"
            f"🆔 Parikara ID: {user_data[user_id]['parikara_id']}\n"
            f"💰 Summa: {user_data[user_id]['amount']} TMT\n"
            f"📞 Klient nomeri: {phone}\n"
            f"⏰ Wagt: {applications[app_id]['time']}\n\n"
            f"<b>Pul geçirilenden soň:</b>"
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tassykla", callback_data=f"confirm_withdraw_{app_id}"),
                InlineKeyboardButton("❌ Ret et", callback_data=f"reject_withdraw_{app_id}")
            ]
        ])
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=group_message,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        
        await update.message.reply_text(
            f"✅ Haýyşyňyz #{app_id} kabul edildi!\n\n"
            "💸 Pul çykarmak haýyşyňyz işlenilýär.\n\n"
            f"🆘 Kömek gerek bolsa: {SUPPORT_USERNAME}"
        )
        
        reset_user_data(user_id)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Ýalňyş telefon nomeri!\n"
            "Dogry format: 65123456 (8 san)\n"
            "Täzeden ýazyň:"
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
                                f"📞 <b>REKWIZITLER #{app_id}</b>\n\n"
                                f"💳 Nomer: <code>{phone}</code>\n"
                                f"💰 Summa: {app['amount']} TMT\n\n"
                                f"Töleg geçireniňizden soň skrinşoty ugradyň!\n\n"
                                f"🆘 Kömek gerek bolsa: {SUPPORT_USERNAME}"
                            ),
                            parse_mode='HTML'
                        )
                        
                        await update.message.reply_text(
                            f"✔ Rekwizitler ugradyldy #{app_id}\n\n"
                            f"👤 Klient: @{app['username']}\n"
                            f"📞 Telefon: {app['phone']}\n"
                            f"📞 Nomer: {phone}\n"
                            f"💰 Summa: {app['amount']} TMT\n\n"
                            f"Skrinşot garaşylýar..."
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
            await update.message.reply_text("❌ Öň registrasiýadan geçmeli! /start basyň.")
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
                    InlineKeyboardButton("✅ Tassykla", callback_data=f"approve_{app_id}"),
                    InlineKeyboardButton("❌ Ret et", callback_data=f"reject_{app_id}")
                ]
            ])
            
            caption = (
                f"🖼 <b>Skrinşot #{app_id}</b>\n\n"
                f"👤 Klient: @{user_app['username']}\n"
                f"📞 Telefon: {user_app['phone']}\n"
                f"💰 Summa: {user_app['amount']} TMT"
            )
            
            await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=file_id,
                caption=caption,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            
            await update.message.reply_text("✅ Skrinşot kabul edildi! Tassyklama garaşyň.")
        else:
            await update.message.reply_text("❌ Aktiw haýyş tapylmady")
    else:
        await update.message.reply_text("❌ Surat ugradyň!")

# ========== ОБРАБОТКА КНОПОК ==========
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    action = data[0]
    
    if action == 'approve':
        app_id = int(data[1])
        
        if app_id not in applications:
            await query.edit_message_caption("❌ Bu haýyş tapylmady")
            return
        
        app = applications[app_id]
        app['status'] = 'completed'
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"✅ <b>TÖLEG TASSYKLANDY #{app_id}</b>\n\n"
                f"💰 Summa: {app['amount']} TMT\n\n"
                f"🆘 Kömek gerek bolsa: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n✅ <b>TASSYKLANDY #{app_id}</b>",
            parse_mode='HTML'
        )
    
    elif action == 'reject' and len(data) == 2:
        app_id = int(data[1])
        
        if app_id not in applications:
            await query.edit_message_caption("❌ Bu haýyş tapylmady")
            return
        
        app = applications[app_id]
        app['status'] = 'rejected'
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"❌ <b>TÖLEG KABUL EDILMEDI #{app_id}</b>\n\n"
                f"💰 Summa: {app['amount']} TMT\n\n"
                f"Ýardam üçin: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n❌ <b>RET EDILDI #{app_id}</b>",
            parse_mode='HTML'
        )
    
    elif action == 'confirm' and data[1] == 'withdraw':
        app_id = int(data[2])
        
        if app_id not in applications:
            await query.edit_message_text("❌ Bu haýyş tapylmady")
            return
        
        app = applications[app_id]
        app['status'] = 'completed'
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"✅ <b>PUL ÇYKARYLDY #{app_id}</b>\n\n"
                f"💰 Summa: {app['amount']} TMT\n\n"
                f"Hyzmat üçin sag boluň! 🤝\n\n"
                f"🆘 Kömek gerek bolsa: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_text(
            text=query.message.text + f"\n\n✅ <b>TASSYKLANDY #{app_id}</b>",
            parse_mode='HTML'
        )
    
    elif action == 'reject' and data[1] == 'withdraw':
        app_id = int(data[2])
        
        if app_id not in applications:
            await query.edit_message_text("❌ Bu haýyş tapylmady")
            return
        
        app = applications[app_id]
        app['status'] = 'rejected'
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"❌ <b>PUL ÇYKARYLMADY #{app_id}</b>\n\n"
                f"💰 Summa: {app['amount']} TMT\n\n"
                f"Ýardam üçin: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_text(
            text=query.message.text + f"\n\n❌ <b>RET EDILDI #{app_id}</b>",
            parse_mode='HTML'
        )

# ========== ОТМЕНА ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_user_data(user_id)
    if context.user_data:
        context.user_data.clear()
    await update.message.reply_text("❌ Amal ýatyryldy.\nTäzeden başlamak üçin /start basyň.")
    return ConversationHandler.END

# ========== ЗАПУСК БОТА ==========
def main():
    global app_counter
    
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()
    time.sleep(2)
    
    print("=" * 60)
    print("🤖 ASTRA KASSA BOT - PAROL SYSTEMASY")
    print("📱 Işe başlady! 24/7 işleýär")
    print("🔐 PAROL DIŇE ADMIN GRUPPA GIDÝÄR!")
    print("👤 Müşderi diňe login alýar")
    print("=" * 60)
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Основной ConversationHandler
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
    application.add_handler(MessageHandler(filters.Regex("^🆘 Ýardam$"), support_button))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=GROUP_CHAT_ID) & ~filters.COMMAND,
        handle_group_message
    ))
    
    print("✅ Bot taýýar!")
    print("👉 Telegramda @Astrakassabot açyň we /start ýazyň")
    print("=" * 60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
