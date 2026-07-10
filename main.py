"""
BarberMan backend server
- SQLite bazada barcha navbatlarni saqlaydi
- Sayt (frontend) shu API bilan gaplashadi
- Telegram bot ham shu bazaga yozadi/o'qiydi
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, date as date_cls
import sqlite3
import os

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
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()


class BookingIn(BaseModel):
    name: str
    phone: str
    service_id: str
    date: str   # YYYY-MM-DD
    time: str   # HH:MM
    source: str = "site"  # "site" yoki "bot"


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

    now = datetime.now()
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

    cur = conn.execute(
        """INSERT INTO bookings (name, phone, service_id, service_name, duration, date, time, source, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (b.name, b.phone, b.service_id, svc["name"], svc["dur"], b.date, b.time, b.source,
         datetime.now().isoformat())
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "message": "Navbat qabul qilindi"}


@app.get("/bookings")
def list_bookings():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM bookings ORDER BY date, time"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
