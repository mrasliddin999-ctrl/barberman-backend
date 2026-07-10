# BarberMan — Backend + Telegram bot ishga tushirish yo'riqnomasi

Bu papkada 4 ta fayl bor:
- `main.py` — backend server (barcha navbatlarni saqlaydi, API beradi)
- `bot.py` — Telegram bot (klientlar shu orqali navbat oladi)
- `requirements.txt` — kerakli python kutubxonalari ro'yxati
- `render.yaml` — Render.com uchun sozlama fayli

---

## 1-QADAM: Bot tokenini bot.py fayliga qo'yish

`bot.py` faylini oching, yuqori qismida shu qatorni toping:

```python
BOT_TOKEN = "BU_YERGA_BOTFATHER_TOKENINI_QOYING"
```

O'rniga BotFather'dan olgan tokeningizni yozing (masalan `123456789:AAHn2...`).

---

## 2-QADAM: Kodni GitHub'ga yuklash

Render.com kodni GitHub orqali oladi. Shuning uchun:

1. https://github.com sahifasiga kiring, akkaunt oching (bepul)
2. Yangi repository (jamg'arma) yarating — nomini masalan `barberman-backend` deb qo'ying
3. Shu 4 ta faylni (`main.py`, `bot.py`, `requirements.txt`, `render.yaml`) o'sha repositoryga yuklang (GitHub saytida "Add file → Upload files" tugmasi orqali oson yuklash mumkin, kod yozish shart emas)

---

## 3-QADAM: Render.com'da serverni ishga tushirish

1. https://render.com saytiga kiring, GitHub akkauntingiz orqali ro'yxatdan o'ting (bepul, kredit karta talab qilinmaydi)
2. "New +" tugmasini bosing → "Blueprint" ni tanlang
3. GitHub repositoryingizni tanlang (`barberman-backend`)
4. Render `render.yaml` faylini avtomatik topib, ikkita xizmatni (backend server va bot) birga yaratadi
5. "Apply" tugmasini bosing va kuting (bir necha daqiqa)

Bir necha daqiqadan so'ng:
- **backend server** ishga tushadi va sizga shunga o'xshash manzil beradi: `https://barberman-api.onrender.com`
- **bot** ham fon rejimida ishga tushadi va Telegram'da javob bera boshlaydi

---

## 4-QADAM: bot.py ichidagi API manzilini yangilash

Backend serveringiz manzilini olgach (3-qadamdan), `bot.py` faylida shu qatorni toping:

```python
API_BASE = "http://localhost:8000"
```

Va o'zgartiring:

```python
API_BASE = "https://barberman-api.onrender.com"
```

(albatta o'zingizning haqiqiy manzilingizni yozing). Keyin GitHub'dagi faylni yangilang — Render avtomatik qayta ishga tushiradi.

---

## 5-QADAM: Saytni backendga ulash

Menga backend serveringiz manzilini ayting (masalan `https://barberman-api.onrender.com`), men saytni (`barberman.html`) shu manzilga ulab, sizga qayta beraman. Shundan keyin:
- Sayt orqali qo'shilgan navbat — botda ham ko'rinadi (band vaqt sifatida)
- Bot orqali qo'shilgan navbat — saytda ham darhol ko'rinadi

---

## Eslatma: Render bepul tarifi haqida

Bepul tarifda server 15 daqiqa harakatsiz tursa "uxlab qoladi" va keyingi so'rovda 30-60 soniya uyg'onish vaqti ketishi mumkin. Agar bu muammo bo'lsa, kelajakda pullik tarifga ($7/oy) o'tish kifoya — hech narsa qayta yozish shart emas.

---

## Yordam kerak bo'lsa

Har bir qadamda qiynalsangiz, menga qaysi qadamda ekaningizni va nima xato chiqqanini ayting — birga hal qilamiz.
