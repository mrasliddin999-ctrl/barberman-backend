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
import time
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


def api_get_with_retry(path, params=None, retries=4, delay=3):
    """Backend server uxlab qolgan bo'lishi mumkin - shuning uchun bir necha marta qayta urinamiz"""
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(f"{API_BASE}{path}", params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_error = e
            time.sleep(delay)
    raise last_error


def api_post_with_retry(path, json_data, retries=4, delay=3):
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.post(f"{API_BASE}{path}", json=json_data, timeout=15)
            return resp
        except Exception as e:
            last_error = e
            time.sleep(delay)
    raise last_error


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text("Bir necha soniya kuting...")
    try:
        services = api_get_with_retry("/services")
    except Exception:
        await wait_msg.edit_text(
            "Serverga ulanib bo'lmadi. Birozdan so'ng qayta /start bosing."
        )
        return ConversationHandler.END

    context.user_data["services"] = services

    buttons = [
        [InlineKeyboardButton(f"{s['name']} ({s['dur']} daq)", callback_data=f"svc:{sid}")]
        for sid, s in services.items()
    ]
    await wait_msg.edit_text(
        "Assalomu alaykum! BarberMan navbat botiga xush kelibsiz.\n\n"
        "Qaysi xizmatni tanlaysiz?\n\n"
        "(Mavjud navbatni bekor qilish uchun /bekor buyrug'ini yozing)",
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
    try:
        data = api_get_with_retry("/slots", params={"date": date_str, "service_id": service_id})
    except Exception:
        await query.edit_message_text(
            "Serverga ulanib bo'lmadi. /start bosib qayta urining."
        )
        return ConversationHandler.END
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
        "chat_id": str(update.effective_chat.id),
    }
    try:
        resp = api_post_with_retry("/bookings", payload)
    except Exception:
        await update.message.reply_text(
            "Serverga ulanib bo'lmadi. /start bosib qayta urining."
        )
        return ConversationHandler.END

    if resp.status_code == 200:
        data = resp.json()
        code = data.get("cancel_code", "----")
        d = datetime.strptime(ud["date"], "%Y-%m-%d")
        await update.message.reply_text(
            f"Navbat qabul qilindi!\n\n"
            f"Xizmat: {svc_name}\n"
            f"Sana: {d.day:02d}.{d.month:02d}.{d.year}\n"
            f"Vaqt: {ud['time']}\n\n"
            f"Bekor qilish kodingiz: {code}\n"
            f"(Navbatni bekor qilish uchun /bekor buyrug'ini bosing va shu kodni kiriting)\n\n"
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


# ---------- navbatni bekor qilish suhbati ----------
CANCEL_PHONE, CANCEL_CODE = range(100, 102)


async def cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Navbatni bekor qilish uchun telefon raqamingizni yozing:"
    )
    return CANCEL_PHONE


async def cancel_enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["cancel_phone"] = update.message.text.strip()
    await update.message.reply_text("Navbat olganda sizga berilgan 6 xonali kodni yozing:")
    return CANCEL_CODE


async def cancel_enter_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    phone = context.user_data.get("cancel_phone", "")

    try:
        resp = api_post_with_retry("/bookings/cancel", {"phone": phone, "cancel_code": code})
    except Exception:
        await update.message.reply_text(
            "Serverga ulanib bo'lmadi. Birozdan so'ng /bekor bosib qayta urining."
        )
        return ConversationHandler.END

    if resp.status_code == 200:
        await update.message.reply_text(
            "Navbatingiz bekor qilindi. Yangi navbat olish uchun /start bosing."
        )
    else:
        await update.message.reply_text(
            "Bunday navbat topilmadi. Telefon raqami yoki kod noto'g'ri. "
            "Qayta urinish uchun /bekor bosing."
        )
    return ConversationHandler.END


async def cancel_abort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilish jarayoni to'xtatildi.")
    return ConversationHandler.END


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ishlayapti")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

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


REMINDER_TEXT = (
    "Soch turmagingizni yangilash vaqti kelib qoldi. "
    "Sizni Dinamo barbershop da kutib qolamiz! "
    "Online navbat olish esdan chiqmasin!"
)

REMINDER_CHECK_INTERVAL = 6 * 60 * 60  # har 6 soatda tekshiradi (soniyada)


async def reminder_loop(app):
    """Fonda ishlab, kerakli klientlarga eslatma yuboradi"""
    while True:
        try:
            data = api_get_with_retry("/reminders/due", retries=1, delay=0)
            due_list = data.get("due", [])
            for item in due_list:
                chat_id = item["chat_id"]
                phone = item["phone"]
                try:
                    await app.bot.send_message(chat_id=chat_id, text=REMINDER_TEXT)
                    api_post_with_retry("/reminders/mark-sent", {"phone": phone}, retries=2, delay=2)
                except Exception as e:
                    print(f"Eslatma yuborishda xato ({phone}): {e}")
        except Exception as e:
            print(f"Reminder tekshiruvida xato: {e}")

        await asyncio.sleep(REMINDER_CHECK_INTERVAL)


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

    cancel_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("bekor", cancel_start)],
        states={
            CANCEL_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_enter_phone)],
            CANCEL_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_enter_code)],
        },
        fallbacks=[CommandHandler("cancel", cancel_abort)],
    )

    app.add_handler(conv_handler)
    app.add_handler(cancel_conv_handler)
    print("Bot ishga tushdi...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # eslatma yuborish vazifasini fonda ishga tushiramiz
    asyncio.create_task(reminder_loop(app))

    # dastur to'xtatilmaguncha ishlab tursin
    stop_event = asyncio.Event()
    await stop_event.wait()


if __name__ == "__main__":
    main()
