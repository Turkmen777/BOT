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
GROUP_CHAT_ID = -1003759188641
ADMIN_GROUP_ID = -1003759188641
SUPPORT_USERNAME = "@astra_kassa"

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
pending_registrations = {}
registered_users = {}

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
    
    if is_registered(user_id):
        return await show_main_menu(update, context)
    
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
    user = update.effective_user
    
    keyboard = [
        [KeyboardButton("💰 Hasaby doldurmak")],
        [KeyboardButton("💸 Pul çykarmak")],
        [KeyboardButton("🆘 Ýardam")]
    ]
    
    welcome_text = (
        f"Hoş geldiňiz, {user.first_name}! 🤖\n\n"
        "Astra Kassa botyna hoş geldiňiz.\n"
        "Hasaby doldurmak ýa-da pul çykarmak üçin aşakdaky düwmeleri ulanyň."
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ConversationHandler.END

# ========== ОТВЕТ НА ВОПРОС ==========
async def handle_client_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "✅ Hawa, men müşderi":
        await update.message.reply_text(
            "📝 <b>GIRIŞ</b>\n\n"
            "Telefon nomeriňizi ýazyň:",
            parse_mode='HTML'
        )
        return LOGIN_PHONE
    
    elif text == "❌ Ýok, täze registrasiýa":
        await update.message.reply_text(
            "📝 <b>TÄZE REGISTRASIÝA</b>\n\n"
            "Telefon nomeriňizi ýazyň:",
            parse_mode='HTML'
        )
        return REG_PHONE
    
    else:
        await update.message.reply_text("Düwmeleri ulanyň!")
        return ASK_CLIENT

# ========== ВХОД ==========
async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "Dogry format: +99365123456 ýa-da 65123456"
        )
        return LOGIN_PHONE

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    if user_id in registered_users and registered_users[user_id]['password'] == password:
        await update.message.reply_text("✅ Giriş üstünlikli!")
        return await show_main_menu(update, context)
    else:
        await update.message.reply_text(
            "❌ Ýalňyş parol!\n"
            f"Ýardam: {SUPPORT_USERNAME}"
        )
        return ConversationHandler.END

# ========== РЕГИСТРАЦИЯ: ТЕЛЕФОН ==========
async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "Dogry format: +99365123456 ýa-da 65123456"
        )
        return REG_PHONE

# ========== РЕГИСТРАЦИЯ: PARIKARA ID ==========
async def reg_parikara_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Проверяем, есть ли сессия
    if user_id not in user_data or 'phone' not in user_data[user_id]:
        await update.message.reply_text("❌ Başdan başlamak üçin /start basyň.")
        return ConversationHandler.END
    
    if validate_parikara_id(text):
        parikara_id = text
        phone = user_data[user_id]['phone']
        password = generate_password()
        user = update.effective_user
        username = user.username or "ýok"
        
        # Сохраняем
        pending_registrations[user_id] = {
            'user_id': user_id,
            'username': username,
            'first_name': user.first_name,
            'phone': phone,
            'parikara_id': parikara_id,
            'password': password,
            'registered_date': datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        
        # Отправляем пароль в группу админу
        admin_message = (
            f"🆕 <b>TÄZE REGISTRASIÝA</b>\n\n"
            f"👤 Ulanyjy: @{username}\n"
            f"📝 Ady: {user.first_name}\n"
            f"📞 Telefon: {phone}\n"
            f"🆔 Parikara ID: {parikara_id}\n"
            f"🔑 PAROL: <code>{password}</code>\n"
            f"⏰ Wagt: {pending_registrations[user_id]['registered_date']}"
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=admin_message,
            parse_mode='HTML'
        )
        
        # Клиенту - только логин
        await update.message.reply_text(
            f"✅ <b>REGISTRASIÝA ÜSTÜNLIKLI</b>\n\n"
            f"📞 Siziň loginiňiz: {phone}\n\n"
            f"🔐 <b>PAROLYŇYZ ADMINDA</b>\n"
            f"Parolyňyzy almak üçin admin bilen habarlaşyň:\n"
            f"{SUPPORT_USERNAME}",
            parse_mode='HTML'
        )
        
        # Очищаем данные
        del user_data[user_id]
        
        # Завершаем разговор
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Ýalňyş! Diňe san giriziň.\n"
            "Parikara ID-nizi täzeden ýazyň:"
        )
        return REG_PARIKARA_ID

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ (support, deposit, withdraw, и т.д.) ==========
# ... (все остальные функции из предыдущего кода)

# ========== ЗАПУСК ==========
def main():
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()
    time.sleep(2)
    
    print("=" * 60)
    print("🤖 ASTRA KASSA BOT - PAROL SYSTEMASY")
    print("📱 Işe başlady! 24/7 işleýär")
    print("🔐 PAROL DIŇE ADMIN GRUPPA GIDÝÄR!")
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
    application.add_handler(MessageHandler(filters.Regex("^🆘 Ýardam$"), support_button))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=GROUP_CHAT_ID) & ~filters.COMMAND,
        handle_group_message
    ))
    
    print("✅ Bot taýýar!")
    print("👉 @Astrakassabot - /start")
    print("=" * 60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
