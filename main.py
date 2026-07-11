"""
BarberMan backend server
- SQLite bazada barcha navbatlarni saqlaydi
- Sayt (frontend) shu API bilan gaplashadi
- Telegram bot ham shu bazaga yozadi/o'qiydi
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, date as date_cls, timezone, timedelta
import sqlite3
import os
import random

# O'zbekiston vaqti (UTC+5) - server odatda UTC bilan ishlaydi
TASHKENT_TZ = timezone(timedelta(hours=5))


def now_tashkent():
    return datetime.now(TASHKENT_TZ)

DB_PATH = os.path.join(os.path.dirname(__file__), "barberman.db")

app = FastAPI(title="BarberMan API")

# Sayt boshqa domendan so'rov yuborishi mumkin bo'lishi uchun
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== SOZLAMALAR (shu yerda o'zgartiring) ======
OPEN_HOUR = 10
CLOSE_HOUR = 23
SERVICES = {
    "hair": {"name": "Soch olish", "dur": 30},
    "beard": {"name": "Soqol olish", "dur": 20},
    "both": {"name": "Soch + Soqol", "dur": 50},
}
# ===================================================


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            service_id TEXT NOT NULL,
            service_name TEXT NOT NULL,
            duration INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            source TEXT DEFAULT 'site',
            cancel_code TEXT,
            created_at TEXT NOT NULL
        )
    """)
    # eski bazalarda cancel_code ustuni bo'lmasligi mumkin - qo'shib qo'yamiz
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN cancel_code TEXT")
    except sqlite3.OperationalError:
        pass  # ustun allaqachon bor

    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            phone TEXT PRIMARY KEY,
            chat_id TEXT,
            last_booking_date TEXT,
            last_reminder_date TEXT
        )
    """)
    conn.commit()
    conn.close()


def generate_cancel_code():
    return str(random.randint(100000, 999999))


init_db()


class BookingIn(BaseModel):
    name: str
    phone: str
    service_id: str
    date: str   # YYYY-MM-DD
    time: str   # HH:MM
    source: str = "site"  # "site" yoki "bot"
    chat_id: str | None = None  # bot orqali kelganda Telegram chat_id


def time_to_min(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def overlaps(existing_bookings, start_min, dur):
    end_min = start_min + dur
    for b in existing_bookings:
        bs = time_to_min(b["time"])
        be = bs + b["duration"]
        if start_min < be and end_min > bs:
            return True
    return False


@app.get("/services")
def get_services():
    return SERVICES


@app.get("/slots")
def get_slots(date: str, service_id: str):
    """Berilgan kun va xizmat uchun bo'sh vaqtlar ro'yxati"""
    if service_id not in SERVICES:
        raise HTTPException(400, "Noto'g'ri xizmat turi")
    dur = SERVICES[service_id]["dur"]

    conn = get_db()
    rows = conn.execute(
        "SELECT time, duration FROM bookings WHERE date = ?", (date,)
    ).fetchall()
    conn.close()
    existing = [{"time": r["time"], "duration": r["duration"]} for r in rows]

    now = now_tashkent()
    is_today = date == now.strftime("%Y-%m-%d")
    now_min = now.hour * 60 + now.minute

    close_min = CLOSE_HOUR * 60
    slots = []
    t = OPEN_HOUR * 60
    while t < close_min:
        if is_today and t <= now_min:
            t += 30
            continue
        if t + dur > close_min:
            t += 30
            continue
        h, m = divmod(t, 60)
        time_str = f"{h:02d}:{m:02d}"
        taken = overlaps(existing, t, dur)
        slots.append({"time": time_str, "taken": taken})
        t += 30

    return {"slots": slots}


@app.post("/bookings")
def create_booking(b: BookingIn):
    if b.service_id not in SERVICES:
        raise HTTPException(400, "Noto'g'ri xizmat turi")
    svc = SERVICES[b.service_id]

    # bandlikni serverda ham qayta tekshiramiz (race-condition oldini olish)
    conn = get_db()
    rows = conn.execute(
        "SELECT time, duration FROM bookings WHERE date = ?", (b.date,)
    ).fetchall()
    existing = [{"time": r["time"], "duration": r["duration"]} for r in rows]

    start_min = time_to_min(b.time)
    if overlaps(existing, start_min, svc["dur"]):
        conn.close()
        raise HTTPException(409, "Bu vaqt band qilib bo'lingan, boshqa vaqt tanlang")

    cancel_code = generate_cancel_code()

    cur = conn.execute(
        """INSERT INTO bookings (name, phone, service_id, service_name, duration, date, time, source, cancel_code, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (b.name, b.phone, b.service_id, svc["name"], svc["dur"], b.date, b.time, b.source, cancel_code,
         now_tashkent().isoformat())
    )

    # klient jadvalini yangilaymiz - yangi navbat sanasi va (agar bot bo'lsa) chat_id
    if b.chat_id:
        conn.execute(
            """INSERT INTO clients (phone, chat_id, last_booking_date, last_reminder_date)
               VALUES (?, ?, ?, NULL)
               ON CONFLICT(phone) DO UPDATE SET
                   chat_id = excluded.chat_id,
                   last_booking_date = excluded.last_booking_date,
                   last_reminder_date = NULL""",
            (b.phone, b.chat_id, b.date)
        )
    else:
        # sayt orqali kelgan bo'lsa ham sanani yangilaymiz, lekin chat_id bo'lmasa eslatma yuborib bo'lmaydi
        conn.execute(
            """INSERT INTO clients (phone, chat_id, last_booking_date, last_reminder_date)
               VALUES (?, NULL, ?, NULL)
               ON CONFLICT(phone) DO UPDATE SET
                   last_booking_date = excluded.last_booking_date,
                   last_reminder_date = NULL""",
            (b.phone, b.date)
        )

    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "cancel_code": cancel_code, "message": "Navbat qabul qilindi"}


@app.get("/bookings")
def list_bookings():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM bookings ORDER BY date, time"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


class CancelIn(BaseModel):
    phone: str
    cancel_code: str


@app.post("/bookings/cancel")
def cancel_booking(c: CancelIn):
    """Klient o'z telefon raqami va kodi orqali navbatini bekor qiladi"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bookings WHERE phone = ? AND cancel_code = ?",
        (c.phone, c.cancel_code)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(404, "Bunday navbat topilmadi. Telefon raqami yoki kod noto'g'ri")

    conn.execute("DELETE FROM bookings WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    return {"message": "Navbat bekor qilindi", "booking": dict(row)}


@app.delete("/bookings/{booking_id}")
def delete_booking(booking_id: int):
    conn = get_db()
    conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    return {"message": "O'chirildi"}


@app.get("/")
def root():
    return {"status": "BarberMan API ishlayapti"}


REMINDER_DAYS = 20


@app.get("/reminders/due")
def get_due_reminders():
    """
    Oxirgi navbatidan REMINDER_DAYS kun o'tgan, chat_id borligi va
    hali shu davr uchun eslatma yuborilmagan klientlar ro'yxati
    """
    conn = get_db()
    rows = conn.execute(
        """SELECT phone, chat_id, last_booking_date, last_reminder_date
           FROM clients
           WHERE chat_id IS NOT NULL AND last_booking_date IS NOT NULL"""
    ).fetchall()
    conn.close()

    today = now_tashkent().date()
    due = []
    for r in rows:
        last_booking = datetime.strptime(r["last_booking_date"], "%Y-%m-%d").date()
        days_passed = (today - last_booking).days

        if days_passed < REMINDER_DAYS:
            continue  # hali vaqti kelmagan

        # agar shu last_booking_date uchun eslatma allaqachon yuborilgan bo'lsa - o'tkazib yuboramiz
        if r["last_reminder_date"] == r["last_booking_date"]:
            continue

        due.append({
            "phone": r["phone"],
            "chat_id": r["chat_id"],
        })

    return {"due": due}


class ReminderSentIn(BaseModel):
    phone: str


@app.post("/reminders/mark-sent")
def mark_reminder_sent(r: ReminderSentIn):
    """Eslatma yuborilgach, shu klientning joriy last_booking_date siga qarab belgilaymiz"""
    conn = get_db()
    row = conn.execute(
        "SELECT last_booking_date FROM clients WHERE phone = ?", (r.phone,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Klient topilmadi")

    conn.execute(
        "UPDATE clients SET last_reminder_date = ? WHERE phone = ?",
        (row["last_booking_date"], r.phone)
    )
    conn.commit()
    conn.close()
    return {"message": "Belgilandi"}
