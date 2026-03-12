import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
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
SUPPORT_USERNAME = "@astra_kassa"  # Контакт поддержки

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
        if amount >= 20:
            return True
    return False

def validate_phone(text):
    """Проверяет 8 цифр"""
    clean_text = re.sub(r'[\s\-\(\)]', '', text)
    return re.match(r'^\d{8}$', clean_text) is not None

def format_phone(text):
    """Добавляет +993 к 8 цифрам"""
    clean_text = re.sub(r'[\s\-\(\)]', '', text)
    return f"+993 {clean_text[:2]} {clean_text[2:5]} {clean_text[5:]}"

# ========== КОМАНДА /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.effective_user
    
    # ТУРКМЕНСКИЕ КНОПКИ (ТЕПЕРЬ С КНОПКОЙ ПОДДЕРЖКИ)
    keyboard = [
        [KeyboardButton("💰 Hasaby doldurmak")],
        [KeyboardButton("💸 Pul çykarmak")],
        [KeyboardButton("🆘 Ýardam")]  # Новая кнопка поддержки
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
    
    # Создаем inline кнопку для быстрого перехода
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Habar ýazmak", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")]
    ])
    
    await update.message.reply_text(
        support_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

# ========== ПОПОЛНЕНИЕ СЧЁТА ==========
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало пополнения"""
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
            "(Iň az 20 TMT, diňe san)"
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
        
        # Получаем username (если есть) или имя
        user = update.effective_user
        username = user.username
        
        # Сохраняем заявку
        applications[app_id] = {
            'id': app_id,
            'user_id': user_id,
            'username': username,
            'first_name': user.first_name,
            'type': 'deposit',
            'parikara_id': user_data[user_id]['parikara_id'],
            'amount': amount,
            'time': datetime.now().strftime("%H:%M %d.%m.%Y"),
            'status': 'waiting_phone'
        }
        
        # Формируем строку с username или именем
        if username:
            user_display = f"@{username}"
        else:
            user_display = user.first_name
        
        # Отправляем в группу
        group_message = (
            f"🆕 <b>TÄZE HAÝYŞ #{app_id}</b>\n\n"
            f"👤 Klient: {user_display}\n"
            f"📞 ID Parikara: {user_data[user_id]['parikara_id']}\n"
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
        
        del user_data[user_id]
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Ýalňyş summa! Iň az 50 TMT bolmaly.\nTäzeden ýazyň:")
        return AMOUNT_INPUT

# ========== ВЫВОД СРЕДСТВ ==========
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало вывода"""
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
        username = user.username
        app_id = app_counter
        app_counter += 1
        
        # Формируем строку с username или именем
        if username:
            user_display = f"@{username}"
        else:
            user_display = user.first_name
        
        # Сохраняем заявку
        applications[app_id] = {
            'id': app_id,
            'user_id': user_id,
            'username': username,
            'first_name': user.first_name,
            'user_display': user_display,
            'type': 'withdraw',
            'parikara_id': user_data[user_id]['parikara_id'],
            'amount': user_data[user_id]['amount'],
            'phone': phone,
            'time': datetime.now().strftime("%H:%M %d.%m.%Y"),
            'status': 'waiting_confirm'
        }
        
        group_message = (
            f"🔴 <b>TÄZE HAÝYŞ: PUL ÇYKARMAK #{app_id}</b>\n\n"
            f"👤 Klient: {user_display}\n"
            f"📞 ID Parikara: {user_data[user_id]['parikara_id']}\n"
            f"💰 Summa: {user_data[user_id]['amount']} TMT\n"
            f"📞 Telefon: {phone}\n"
            f"⏰ Wagt: {applications[app_id]['time']}\n\n"
            f"<b>Pul geçirilenden soň:</b>"
        )
        
        # Кнопка для подтверждения вывода
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Töleg tassykla", callback_data=f"confirm_withdraw_{app_id}")]
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
    """Обрабатывает сообщения в группе (отправка реквизитов)"""
    if update.effective_chat.id != GROUP_CHAT_ID:
        return
    
    text = update.message.text.strip()
    
    # Проверяем, что это 8 цифр
    if re.match(r'^\d{8}$', text):
        # Проверяем, есть ли это сообщение как ответ на другое
        if update.message.reply_to_message:
            # Это ответ на сообщение - ищем заявку
            original_text = update.message.reply_to_message.text or ""
            
            # Ищем номер заявки
            match = re.search(r'#(\d+)', original_text)
            if match:
                app_id = int(match.group(1))
                if app_id in applications:
                    app = applications[app_id]
                    
                    if app['type'] == 'deposit':
                        phone = format_phone(text)
                        
                        # Отправляем клиенту
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
                        
                        # Отправляем подтверждение в группу
                        await update.message.reply_text(
                            f"✔ Rekwizitler ugradyldy #{app_id}\n\n"
                            f"👤 Klient: {app.get('user_display', app['first_name'])}\n"
                            f"📞 Nomer: {phone}\n"
                            f"💰 Summa: {app['amount']} TMT\n\n"
                            f"Skrinşot garaşylýar..."
                        )
                        
                        # Обновляем статус
                        app['status'] = 'waiting_screenshot'
                        app['phone'] = phone
                        return
                    else:
                        await update.message.reply_text(f"❌ #{app_id} - bu çykaryş üçin däl")
                        return
                else:
                    await update.message.reply_text(f"❌ #{app_id} belgili haýyş tapylmady")
                    return
        
        # Если это не ответ на сообщение, но 8 цифр
        else:
            # Ищем последнюю активную заявку
            last_app = None
            for app_id, app in applications.items():
                if app['type'] == 'deposit' and app['status'] == 'waiting_phone':
                    last_app = app
                    break
            
            if last_app:
                phone = format_phone(text)
                
                # Отправляем клиенту
                await context.bot.send_message(
                    chat_id=last_app['user_id'],
                    text=(
                        f"📞 <b>REKWIZITLER #{last_app['id']}</b>\n\n"
                        f"💳 Nomer: <code>{phone}</code>\n"
                        f"💰 Summa: {last_app['amount']} TMT\n\n"
                        f"Töleg geçireniňizden soň skrinşoty ugradyň!\n\n"
                        f"🆘 Kömek gerek bolsa: {SUPPORT_USERNAME}"
                    ),
                    parse_mode='HTML'
                )
                
                # Отправляем подтверждение в группу
                await update.message.reply_text(
                    f"✔ Rekwizitler ugradyldy #{last_app['id']}\n\n"
                    f"👤 Klient: {last_app.get('user_display', last_app['first_name'])}\n"
                    f"📞 Nomer: {phone}\n"
                    f"💰 Summa: {last_app['amount']} TMT\n\n"
                    f"Skrinşot garaşylýar..."
                )
                
                # Обновляем статус
                last_app['status'] = 'waiting_screenshot'
                last_app['phone'] = phone
            else:
                await update.message.reply_text("❌ Açyk haýyş tapylmady")

# ========== ОБРАБОТКА СКРИНШОТОВ ==========
async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает получение скриншотов"""
    if update.message.photo:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        user = update.effective_user
        username = user.username
        
        # Формируем строку с username или именем
        if username:
            user_display = f"@{username}"
        else:
            user_display = user.first_name
        
        # Ищем активную заявку пользователя
        user_app = None
        for app_id, app in applications.items():
            if app['user_id'] == user.id and app['status'] == 'waiting_screenshot':
                user_app = app
                break
        
        if user_app:
            app_id = user_app['id']
            
            # Сохраняем file_id скриншота
            applications[app_id]['screenshot_id'] = file_id
            
            # Отправляем в группу с кнопкой подтверждения
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Töleg tassykla", callback_data=f"approve_{app_id}")]
            ])
            
            caption = (
                f"🖼 <b>Skrinşot #{app_id}</b>\n\n"
                f"👤 Klient: {user_display}\n"
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
    """Обрабатывает нажатия на кнопки"""
    query = update.callback_query
    await query.answer()
    
    # Разбираем callback_data
    data = query.data.split('_')
    action = data[0]
    
    if action == 'approve':
        app_id = int(data[1])
        
        if app_id not in applications:
            await query.edit_message_caption("❌ Bu haýyş tapylmady")
            return
        
        app = applications[app_id]
        app['status'] = 'completed'
        
        # Получаем display имени для клиента
        if app.get('username'):
            user_display = f"@{app['username']}"
        else:
            user_display = app['first_name']
        
        # Отправляем сообщение клиенту
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"✅ <b>SARGYT TASSYKLANDY #{app_id}</b>\n\n"
                f"👤 Klient: {user_display}\n"
                f"💰 Summa: {app['amount']} TMT\n"
                f"✅ Tassyklandy: Admin\n\n"
                f"🆘 Kömek gerek bolsa: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        # Обновляем сообщение в группе
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n✅ <b>SARGYT TASSYKLANDY #{app_id}</b>\n\n👤 Klient: {user_display}\n💰 Summa: {app['amount']} TMT\n✅ Tassyklandy: Admin",
            parse_mode='HTML'
        )
        
        # Отправляем подтверждение в группу
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"✅ #{app_id} tassyklanyldy"
        )
    
    elif action == 'confirm' and data[1] == 'withdraw':
        app_id = int(data[2])
        
        if app_id not in applications:
            await query.edit_message_text("❌ Bu haýyş tapylmady")
            return
        
        app = applications[app_id]
        app['status'] = 'completed'
        
        # Получаем display имени для клиента
        if app.get('username'):
            user_display = f"@{app['username']}"
        else:
            user_display = app['first_name']
        
        await context.bot.send_message(
            chat_id=app['user_id'],
            text=(
                f"✅ <b>PUL ÇYKARYLDY #{app_id}</b>\n\n"
                f"👤 Klient: {user_display}\n"
                f"💰 Summa: {app['amount']} TMT\n\n"
                f"Hyzmat üçin sag boluň! 🤝\n\n"
                f"🆘 Kömek gerek bolsa: {SUPPORT_USERNAME}"
            ),
            parse_mode='HTML'
        )
        
        await query.edit_message_text(
            text=query.message.text + f"\n\n✅ <b>TASSYKLANDY #{app_id}</b>\n\n👤 Klient: {user_display}\n💰 Summa: {app['amount']} TMT",
            parse_mode='HTML'
        )

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
    print("💰 KNOpkalar: 'Hasaby doldurmak', 'Pul çykarmak', '🆘 Ýardam'")
    print(f"👥 Ýardam: {SUPPORT_USERNAME}")
    print("=" * 60)
    
    # Создаем приложение бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ConversationHandler для пополнения счета
    deposit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Hasaby doldurmak$"), deposit_start)],
        states={
            PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_phone)],
            AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # ConversationHandler для вывода средств
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
    application.add_handler(MessageHandler(filters.Regex("^🆘 Ýardam$"), support_button))
    application.add_handler(deposit_conv)
    application.add_handler(withdraw_conv)
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Обработчик сообщений в группе (для 8 цифр)
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


