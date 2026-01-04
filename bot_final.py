import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from flask import Flask
import threading
import time

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram Bot Parikara работает 24/7!"

@app.route('/ping')
def ping():
    return "🏓 Pong"

def run_flask():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ========== НАСТРОЙКИ БОТА ==========
BOT_TOKEN = "8123803682:AAFOgF4Ssp95WkxRwQcjfao9qnMnA6pMVQI"
GROUP_CHAT_ID = -1003663534213
ADMIN_IDS = [8444800411]
MIN_AMOUNT = 50

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

deposits = []
next_id = 1000
WAITING_ID, WAITING_AMOUNT = range(2)

# ========== КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    keyboard = [
        [KeyboardButton("💰 Пополнить счет")],
        [KeyboardButton("🆘 Помощь")]
    ]
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    )
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки Помощь"""
    help_text = """
🆘 <b>Как пополнить счет:</b>

1. Нажмите '💰 Пополнить счет'
2. Введите ваш ID в системе Parikara
3. Введите сумму (от 50 TMT)
4. Ожидайте реквизиты от администратора
5. Оплатите по реквизитам
6. Отправьте скриншот оплаты
7. Ждите подтверждения

<b>Контакты:</b>
• Поддержка: @parikara_support
• Сайт: www.parikara.com

<b>Чтобы бот работал 24/7:</b>
• Просто пишите боту раз в день
• Или нажимайте /start
    """
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def help_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /help"""
    await help_command(update, context)

async def handle_deposit_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки Пополнить счет"""
    await update.message.reply_text("Введите ваш ID в системе Parikara:")
    return WAITING_ID

async def handle_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['client_id'] = update.message.text
    await update.message.reply_text(f"Введите сумму (мин. {MIN_AMOUNT} TMT):")
    return WAITING_AMOUNT

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(',', '.'))
        if amount < MIN_AMOUNT:
            await update.message.reply_text(f"❌ Минимум {MIN_AMOUNT} TMT")
            return WAITING_AMOUNT
        
        global next_id, deposits
        deposit = {
            'id': next_id,
            'user_id': update.effective_user.id,
            'user_name': update.effective_user.first_name,
            'client_id': context.user_data['client_id'],
            'amount': amount,
            'time': datetime.now().strftime("%H:%M %d.%m.%Y"),
            'status': 'waiting'
        }
        deposits.append(deposit)
        
        await update.message.reply_text(f"✅ Заявка #{next_id} принята!\nОжидайте реквизиты...")
        
        # Отправка в группу
        group_text = f"""🆕 <b>НОВАЯ ЗАЯВКА #{next_id}</b>

👤 Клиент: {update.effective_user.first_name}
📞 ID Parikara: {context.user_data['client_id']}
💰 Сумма: {amount} TMT
⏰ Время: {deposit['time']}

<b>Отправьте номер телефона для клиента:</b>
(8 цифр, например: 65656565)"""
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=group_text,
            parse_mode='HTML'
        )
        
        next_id += 1
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число!")
        return WAITING_AMOUNT

async def handle_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_CHAT_ID:
        return
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    text = update.message.text.strip()
    if text.isdigit() and len(text) == 8:
        last_deposit = None
        for deposit in deposits:
            if deposit['status'] == 'waiting' and 'phone' not in deposit:
                last_deposit = deposit
                break
        
        if not last_deposit:
            await update.message.reply_text("❌ Нет заявок, ожидающих номер")
            return
        
        phone = f"+993 {text[:2]} {text[2:5]} {text[5:]}"
        last_deposit['phone'] = phone
        
        await context.bot.send_message(
            chat_id=last_deposit['user_id'],
            text=f"💳 <b>РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ</b>\n\n📱 Номер: <code>{phone}</code>\n💰 Сумма: {last_deposit['amount']} TMT\n\nПосле оплаты отправьте скриншот!",
            parse_mode='HTML'
        )
        
        keyboard = [[InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{last_deposit['id']}")]]
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"⏳ Ожидаем скриншот от клиента #{last_deposit['id']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_deposit = None
    for deposit in deposits:
        if deposit['user_id'] == user_id and deposit.get('phone') and deposit['status'] == 'waiting':
            user_deposit = deposit
            break
    
    if not user_deposit:
        await update.message.reply_text("❌ Нет активной заявки")
        return
    
    await update.message.reply_text("✅ Скриншот получен! Ожидайте подтверждения")
    photo = update.message.photo[-1]
    await context.bot.send_photo(
        chat_id=GROUP_CHAT_ID,
        photo=photo.file_id,
        caption=f"📸 Скриншот оплаты #{user_deposit['id']}"
    )
    
    keyboard = [[InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{user_deposit['id']}")]]
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=f"✅ Скриншот получен от клиента #{user_deposit['id']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("confirm_"):
        deposit_id = int(query.data.split("_")[1])
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Только администратор", show_alert=True)
            return
        
        deposit = None
        for d in deposits:
            if d['id'] == deposit_id:
                deposit = d
                break
        
        if deposit:
            deposit['status'] = 'completed'
            await query.edit_message_text(f"✅ <b>ПЛАТЕЖ ПОДТВЕРЖДЕН #{deposit_id}</b>", parse_mode='HTML')
            await context.bot.send_message(
                chat_id=deposit['user_id'],
                text=f"🎉 <b>Счет пополнен!</b>\n\n💰 Сумма: {deposit['amount']} TMT\n🆔 Заявка: #{deposit_id}",
                parse_mode='HTML'
            )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено")
    return ConversationHandler.END

# ========== ЗАПУСК БОТА ==========
def main():
    # Запускаем веб-сервер для Render
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()
    time.sleep(2)
    
    print("=" * 50)
    print("🤖 БОТ PARIKARA ЗАПУЩЕН!")
    print("📱 Две кнопки: Пополнить счет и Помощь")
    print("🌐 Веб-сервер: порт 10000")
    print("=" * 50)
    
    # Создаем приложение бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ConversationHandler для пополнения счета
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Пополнить счет$"), handle_deposit_button)],
        states={
            WAITING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id)],
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_text_command))
    application.add_handler(MessageHandler(filters.Regex("^🆘 Помощь$"), help_command))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Обработчик сообщений в группе
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=GROUP_CHAT_ID) & ~filters.COMMAND,
        handle_group_text
    ))
    
    print("✅ Бот готов к работе!")
    print("👉 Напишите /start в Telegram")
    print("=" * 50)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()