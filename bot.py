"""
BarberMan Telegram bot
Klient bilan qadam-baqadam suhbatlashib, navbat oladi va shu bazaga yozadi.

ISHGA TUSHIRISH:
1. pip install python-telegram-bot requests
2. Pastdagi BOT_TOKEN o'rniga o'zingizning BotFather'dan olgan tokeningizni qo'ying
3. API_BASE ni backend serveringiz manziliga o'zgartiring (masalan https://barberman-api.onrender.com)
4. python bot.py
"""

import logging
import os
import asyncio
import threading
import requests
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)

# ====== SOZLAMALAR (shu yerga o'zingiznikini yozing) ======
BOT_TOKEN = "8057506323:AAFydu8hAkLjj26MSHWSYr3RwySOcou3iLs"
API_BASE = "https://barberman-api-23cb.onrender.com"   # backend server manzili
# =============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# suhbat bosqichlari
CHOOSE_SERVICE, CHOOSE_DATE, CHOOSE_TIME, ENTER_NAME, ENTER_PHONE = range(5)

DOW_UZ = ['Dush', 'Sesh', 'Chor', 'Pay', 'Jum', 'Shan', 'Yak']


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resp = requests.get(f"{API_BASE}/services")
    services = resp.json()
    context.user_data["services"] = services

    buttons = [
        [InlineKeyboardButton(f"{s['name']} ({s['dur']} daq)", callback_data=f"svc:{sid}")]
        for sid, s in services.items()
    ]
    await update.message.reply_text(
        "Assalomu alaykum! BarberMan navbat botiga xush kelibsiz.\n\n"
        "Qaysi xizmatni tanlaysiz?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CHOOSE_SERVICE


async def choose_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.split(":")[1]
    context.user_data["service_id"] = service_id

    # kelasi 7 kunni ko'rsatamiz
    buttons = []
    today = datetime.now()
    for i in range(7):
        d = today + timedelta(days=i)
        label = f"{DOW_UZ[d.weekday()]} {d.day}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"date:{d.strftime('%Y-%m-%d')}")])

    await query.edit_message_text(
        "Qaysi kunga yozilmoqchisiz?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CHOOSE_DATE


async def choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date_str = query.data.split(":")[1]
    context.user_data["date"] = date_str

    service_id = context.user_data["service_id"]
    resp = requests.get(f"{API_BASE}/slots", params={"date": date_str, "service_id": service_id})
    data = resp.json()
    slots = data["slots"]

    free_slots = [s for s in slots if not s["taken"]]
    if not free_slots:
        await query.edit_message_text(
            "Bu kunda bo'sh vaqt qolmagan. /start bosib boshqa kunni tanlang."
        )
        return ConversationHandler.END

    buttons = []
    row = []
    for i, s in enumerate(free_slots):
        row.append(InlineKeyboardButton(s["time"], callback_data=f"time:{s['time']}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await query.edit_message_text(
        "Qaysi soatga yozilmoqchisiz?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CHOOSE_TIME


async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    time_str = query.data.split(":", 1)[1]
    context.user_data["time"] = time_str

    await query.edit_message_text("Ismingizni yozing:")
    return ENTER_NAME


async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Telefon raqamingizni yozing (masalan +998901234567):")
    return ENTER_PHONE


async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text.strip()
    ud = context.user_data
    services = ud["services"]
    svc_name = services[ud["service_id"]]["name"]

    payload = {
        "name": ud["name"],
        "phone": ud["phone"],
        "service_id": ud["service_id"],
        "date": ud["date"],
        "time": ud["time"],
        "source": "bot",
    }
    resp = requests.post(f"{API_BASE}/bookings", json=payload)

    if resp.status_code == 200:
        d = datetime.strptime(ud["date"], "%Y-%m-%d")
        await update.message.reply_text(
            f"Navbat qabul qilindi!\n\n"
            f"Xizmat: {svc_name}\n"
            f"Sana: {d.day:02d}.{d.month:02d}.{d.year}\n"
            f"Vaqt: {ud['time']}\n\n"
            f"Kutib qolamiz! Yangi navbat uchun /start bosing."
        )
    else:
        await update.message.reply_text(
            "Afsuski bu vaqt band qilib bo'lindi. Qayta urinish uchun /start bosing."
        )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi. Qayta boshlash uchun /start bosing.")
    return ConversationHandler.END


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ishlayapti")

    def log_message(self, format, *args):
        pass  # keraksiz loglarni o'chirish


def _run_fake_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    server.serve_forever()


def main():
    # Render "web service" portni tinglashni talab qiladi, shuning uchun
    # fon rejimida kichik soxta server ishga tushiramiz
    threading.Thread(target=_run_fake_server, daemon=True).start()

    asyncio.run(run_bot())


async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_SERVICE: [CallbackQueryHandler(choose_service, pattern="^svc:")],
            CHOOSE_DATE: [CallbackQueryHandler(choose_date, pattern="^date:")],
            CHOOSE_TIME: [CallbackQueryHandler(choose_time, pattern="^time:")],
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name)],
            ENTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    print("Bot ishga tushdi...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # dastur to'xtatilmaguncha ishlab tursin
    stop_event = asyncio.Event()
    await stop_event.wait()


if __name__ == "__main__":
    main()
