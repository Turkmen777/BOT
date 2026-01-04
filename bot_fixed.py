import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8123803682:AAFOgF4Ssp95WkxRwQcjfao9qnMnA6pMVQI"  # ⚠️ ВАШ ТОКЕН
GROUP_CHAT_ID = -1003663534213
ADMIN_IDS = [8444800411]
MIN_AMOUNT = 50

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

deposits = []
next_id = 1000
WAITING_ID, WAITING_AMOUNT = range(2)

# ========== КЛИЕНТСКАЯ ЧАСТЬ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("💰 Пополнить счет")]]
    await update.message.reply_text(
        "Привет! Нажмите кнопку:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_deposit_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите ваш ID:")
    return WAITING_ID

async def handle_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['client_id'] = update.message.text
    await update.message.reply_text("Введите сумму (мин. 50 TMT):")
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
        group_text = f"""
🆕 <b>НОВАЯ ЗАЯВКА #{next_id}</b>

👤 Клиент: {update.effective_user.first_name}
📞 ID: {context.user_data['client_id']}
💰 Сумма: {amount} TMT
⏰ Время: {deposit['time']}

<b>Отправьте номер телефона для клиента:</b>
(8 цифр, например: 65656565)
        """
        
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

# ========== ОБРАБОТКА ГРУППЫ ==========
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

# ========== ОСТАЛЬНОЙ КОД ==========
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

# ========== ЗАПУСК ==========
def main():
    print("=" * 50)
    print("🤖 ЗАПУСКАЕМ БОТА...")
    print("=" * 50)
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Пополнить счет$"), handle_deposit_button)],
        states={
            WAITING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id)],
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=GROUP_CHAT_ID) & ~filters.COMMAND,
        handle_group_text
    ))
    
    print("✅ Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    main()