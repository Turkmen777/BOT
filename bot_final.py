import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from flask import Flask
import threading
import time
import re

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

# Состояния для разговоров
(PHONE_INPUT, AMOUNT_INPUT, WITHDRAW_PHONE_INPUT, 
 WITHDRAW_AMOUNT_INPUT, WITHDRAW_RECEIPT_INPUT) = range(5)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище данных
user_data = {}
applications = {}
app_counter = 1000

# ========== ФУНКЦИИ ДЛЯ ПРОВЕРКИ ==========
def validate_parikara_id(text):
    """Проверяет, что введены только цифры"""
    return re.match(r'^\d+$', text) is not None

def validate_amount(text):
    """Проверяет сумму (минимум 30 TMT)"""
    if re.match(r'^\d+$', text):
        amount = int(text)
        if amount >= 30:
            return True
    return False

def validate_phone(text):
    """Проверяет 8 цифр"""
    clean_text = re.sub(r'[\s\-\(\)]', '', text)
    return re.match(r'^\d{8}$', clean_text) is not None

def format_phone(text):
    """Добавляет +993 к 8 цифрам"""
    clean_text = re.sub(r'[\s\-\(\)]', '', text)
    return f"+993{clean_text}"

# ========== КОМАНДА /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.effective_user
    
    # ТУРКМЕНСКИЕ КНОПКИ
    keyboard = [
        [KeyboardButton("💰 Hasaby doldurmak")],  # Пополнить счет
        [KeyboardButton("💸 Pul çykarmak")]       # Вывести деньги
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

# ========== ПОПОЛНЕНИЕ СЧЁТА (TÜRKMENÇE) ==========
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало пополнения - кнопка "Hasaby doldurmak" """
    user_id = update.effective_user.id
    user_data[user_id] = {'action': 'deposit'}
    await update.message.reply_text("🔑 Parikara ID-nizi ýazyň:\n(Diňe sanlar)")
    return PHONE_INPUT

async def deposit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ID"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
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
    """Получение суммы и отправка в группу"""
    global app_counter
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_amount(text):
        amount = text
        user_data[user_id]['amount'] = amount
        app_id = app_counter
        app_counter += 1
        
        # Сохраняем заявку
        applications[app_id] = {
            'id': app_id,
            'user_id': user_id,
            'username': update.effective_user.username or "ýok",
            'type': 'deposit',
            'parikara_id': user_data[user_id]['parikara_id'],
            'amount': amount,
            'time': datetime.now().strftime("%d.%m.%Y %H:%M"),
            'status': 'waiting'
        }
        
        # Отправляем в группу
        user = update.effective_user
        username = user.username or "ýok"
        
        group_message = (
            f"🟢 TÄZE HAÝYŞ: HASABY DOLDURMAK #{app_id}\n\n"
            f"Ulanyjy: @{username}\n"
            f"ID: {user_data[user_id]['parikara_id']}\n"
            f"Summa: {amount} TMT\n"
            f"Wagt: {applications[app_id]['time']}\n\n"
            f"📞 Rekwizitleri ugratmak üçin:\n"
            f"Bu habara jogap edip 8 san ýazyň (mysal: 65656565)"
        )
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=group_message
        )
        
        await update.message.reply_text(
            f"✅ Haýyşyňyz #{app_id} kabul edildi!\n\n"
            "📞 Töleg maglumatlary 10 minudyň içinde ugradylar.\n"
            "Tölegiňizi geçireniňizden soň, skrinşoty ugratmagy unutmaň."
        )
        
        del user_data[user_id]
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Ýalňyş summa! Iň az 30 TMT bolmaly.\nTäzeden ýazyň:")
        return AMOUNT_INPUT

# ========== ВЫВОД СРЕДСТВ (TÜRKMENÇE) ==========
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало вывода - кнопка "Pul çykarmak" """
    user_id = update.effective_user.id
    user_data[user_id] = {'action': 'withdraw'}
    await update.message.reply_text("🔑 Parikara ID-nizi ýazyň:\n(Diňe sanlar)")
    return WITHDRAW_PHONE_INPUT

async def withdraw_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ID для вывода"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
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
    """Получение суммы вывода"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
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
    """Получение телефона и отправка в группу"""
    global app_counter
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_phone(text):
        phone = format_phone(text)
        user = update.effective_user
        username = user.username or "ýok"
        app_id = app_counter
        app_counter += 1
        
        # Сохраняем заявку
        applications[app_id] = {
            'id': app_id,
            'user_id': user_id,
            'username': username,
            'type': 'withdraw',
            'parikara_id': user_data[user_id]['parikara_id'],
            'amount': user_data[user_id]['amount'],
            'phone': phone,
            'time': datetime.now().strftime("%d.%m.%Y %H:%M"),
            'status': 'waiting'
        }
        
        group_message = (
            f"🔴 TÄZE HAÝYŞ: PUL ÇYKARMAK #{app_id}\n\n"
            f"Ulanyjy: @{username}\n"
            f"ID: {user_data[user_id]['parikara_id']}\n"
            f"Summa: {user_data[user_id]['amount']} TMT\n"
            f"Telefon: {phone}\n"
            f"Wagt: {applications[app_id]['time']}\n\n"
            f"✅ Pul geçirilenden soň:\n"
            f"Bu habara 'ok' ýazyň"
        )
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=group_message
        )
        
        await update.message.reply_text(
            f"✅ Haýyşyňyz #{app_id} kabul edildi!\n\n"
            "💸 Pul çykarmak haýyşyňyz işlenilýär.\n"
            "Administratorlar tizara habarlaşarlar."
        )
        
        del user_data[user_id]
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
    """Обрабатывает сообщения в группе"""
    if update.effective_chat.id != GROUP_CHAT_ID:
        return
    
    # Проверяем, что это ответ на другое сообщение
    if update.message.reply_to_message:
        original_text = update.message.reply_to_message.text or ""
        
        # Ищем номер заявки
        match = re.search(r'#(\d+)', original_text)
        if match:
            app_id = int(match.group(1))
            if app_id in applications:
                app = applications[app_id]
                admin_message = update.message.text.strip()
                
                # ЕСЛИ 8 ЦИФР - ОТПРАВЛЯЕМ РЕКВИЗИТЫ (для пополнения)
                if re.match(r'^\d{8}$', admin_message) and app['type'] == 'deposit':
                    phone = f"+993{admin_message}"
                    
                    await context.bot.send_message(
                        chat_id=app['user_id'],
                        text=(
                            f"📞 TÖLEG MAGLUMATLARY #{app_id}\n\n"
                            f"Pul geçirmeli nomer:\n"
                            f"{phone}\n\n"
                            f"💰 Summa: {app['amount']} TMT\n\n"
                            f"Pul geçireniňizden soň, skrinşoty ugradyň."
                        )
                    )
                    
                    await update.message.reply_text(f"✅ {phone} nomeri ugradyldy")
                    app['status'] = 'phone_sent'
                
                # ЕСЛИ "OK" - ПОДТВЕРЖДАЕМ ВЫВОД
                elif admin_message.lower() == 'ok' and app['type'] == 'withdraw':
                    app['status'] = 'completed'
                    await context.bot.send_message(
                        chat_id=app['user_id'],
                        text=f"✅ PUL ÇYKARYLDY #{app_id}\n\n💰 Summa: {app['amount']} TMT"
                    )
                    await update.message.reply_text(f"✅ #{app_id} tassyklanyldy")

# ========== ОБРАБОТКА СКРИНШОТОВ ==========
async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает получение скриншотов"""
    if update.message.photo:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        user = update.effective_user
        username = user.username or "ýok"
        
        # Ищем активную заявку пользователя
        user_app = None
        for app_id, app in applications.items():
            if app['user_id'] == user.id and app['status'] in ['waiting', 'phone_sent']:
                user_app = app
                break
        
        if user_app:
            app_id = user_app['id']
            # Отправляем в группу
            await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=file_id,
                caption=f"🖼 TÄZE SKRINŞOT #{app_id}\n\nUlanyjy: @{username}"
            )
            
            await update.message.reply_text("✅ Skrinşot kabul edildi! Tassyklama garaşyň.")
            
            # Ждём подтверждения от админа
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"#{app_id} - Skrinşot geldi. Tassyklamak üçin 'ok' ýazyň"
            )
        else:
            await update.message.reply_text("❌ Aktiw haýyş tapylmady")
    else:
        await update.message.reply_text("❌ Surat ugradyň!")

# ========== ОТМЕНА ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена действия"""
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
    await update.message.reply_text("❌ Amal ýatyryldy.\nTäzeden başlamak üçin /start basyň.")
    return ConversationHandler.END

# ========== ЗАПУСК БОТА ==========
def main():
    # Запускаем веб-сервер
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()
    time.sleep(2)
    
    print("=" * 60)
    print("🤖 ASTRA KASSA BOT - TÜRKMENÇE VERSION")
    print("📱 Işe başlady! 24/7 işleýär")
    print("💰 KNOpkalar: 'Hasaby doldurmak' we 'Pul çykarmak'")
    print("👥 ADMIN FUNKSIÝALARY:")
    print("   • 8 san ýaz -> +993 goşulyp müşderä gidýär")
    print("   • 'ok' ýaz -> tassyklaýar")
    print("=" * 60)
    
    # Создаем приложение бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ConversationHandler для пополнения счета (TÜRKMENÇE)
    deposit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Hasaby doldurmak$"), deposit_start)],
        states={
            PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_phone)],
            AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # ConversationHandler для вывода средств (TÜRKMENÇE)
    withdraw_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Pul çykarmak$"), withdraw_start)],
        states={
            WITHDRAW_PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone)],
            WITHDRAW_AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_RECEIPT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_receipt)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(deposit_conv)
    application.add_handler(withdraw_conv)
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    
    # Обработчик сообщений в группе
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=GROUP_CHAT_ID) & ~filters.COMMAND,
        handle_group_message
    ))
    
    print("✅ Bot taýýar!")
    print("👉 Telegramda @Astrakassabot açyň we /start ýazyň")
    print("=" * 60)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
