# ============================================================
# @caloriiibot — бот подсчёта КБЖУ
# Деплой: Railway (добавь переменную BOT_TOKEN в Variables)
# ============================================================
import asyncio
import io
import json
import logging
import os
import random
import re
import sqlite3
from datetime import date, datetime, timedelta

import requests
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (BufferedInputFile, CallbackQuery,
                           InlineKeyboardButton, InlineKeyboardMarkup,
                           Message)

# ── НАСТРОЙКИ ────────────────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]          # Railway → Variables → BOT_TOKEN
SPOONACULAR = os.getenv("SPOONACULAR_KEY", "") # опционально
BOT_USERNAME = os.getenv("BOT_USERNAME", "caloriiibot")
DB_PATH     = os.getenv("DB_PATH", "food.db")
MODEL_PATH  = "food_model.tflite"
LABELS_PATH = "labels.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("caloriiibot")

# ── ОПЦИОНАЛЬНЫЕ БИБЛИОТЕКИ (graceful degradation) ───────────
try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:
    try:
        from tensorflow.lite import Interpreter   # type: ignore
    except ImportError:
        Interpreter = None

try:
    from pyzbar.pyzbar import decode as zbar_decode
except ImportError:
    zbar_decode = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ── БАЗА ДАННЫХ ───────────────────────────────────────────────
con = sqlite3.connect(DB_PATH, check_same_thread=False)
con.row_factory = sqlite3.Row
con.execute("PRAGMA journal_mode=WAL")

def q(sql, params=()):
    cur = con.execute(sql, params)
    con.commit()
    return cur

def today():
    return date.today().isoformat()

def ensure_tables():
    con.executescript("""
    CREATE TABLE IF NOT EXISTS foods (
        class_id INTEGER PRIMARY KEY, en_name TEXT UNIQUE, name TEXT,
        calories_per_100g REAL, protein REAL, fat REAL, carbs REAL,
        typical_portion INTEGER DEFAULT 100
    );
    CREATE TABLE IF NOT EXISTS meals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        date TEXT NOT NULL, meal_name TEXT, grams REAL,
        calories REAL, protein REAL, fat REAL, carbs REAL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_meals ON meals(user_id, date);
    CREATE TABLE IF NOT EXISTS water (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, date TEXT NOT NULL, ml INTEGER
    );
    CREATE TABLE IF NOT EXISTS exercises (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        date TEXT NOT NULL, kind TEXT, detail TEXT, calories_burned REAL
    );
    CREATE TABLE IF NOT EXISTS goals (
        user_id INTEGER PRIMARY KEY,
        daily_calories INTEGER DEFAULT 2000,
        water_reminders INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS achievements (
        user_id INTEGER NOT NULL, code TEXT NOT NULL,
        earned_at TEXT DEFAULT (datetime('now')), PRIMARY KEY (user_id, code)
    );
    """)

ensure_tables()

# ── МОДЕЛЬ ────────────────────────────────────────────────────
interpreter = None
labels = []
if Interpreter and os.path.exists(MODEL_PATH):
    interpreter = Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    _inp = interpreter.get_input_details()[0]
    _out = interpreter.get_output_details()[0]
    log.info("TFLite модель загружена")
if os.path.exists(LABELS_PATH):
    labels = open(LABELS_PATH).read().splitlines()

def classify_food(img: Image.Image):
    if not interpreter:
        return None
    x = np.asarray(img.convert("RGB").resize((224, 224)), dtype=np.float32)[None] / 255.0
    interpreter.set_tensor(_inp["index"], x)
    interpreter.invoke()
    probs = interpreter.get_tensor(_out["index"])[0]
    cid = int(np.argmax(probs))
    return cid, float(probs[cid])

def food_by_class(cid):
    return q("SELECT * FROM foods WHERE class_id=?", (cid,)).fetchone()

# ── ШТРИХ-КОД + OPEN FOOD FACTS ──────────────────────────────
def scan_barcode(img: Image.Image):
    if not zbar_decode:
        return None
    for r in zbar_decode(img):
        if r.type in ("EAN13", "EAN8", "UPCA", "UPCE"):
            return r.data.decode()
    return None

def off_product(barcode: str):
    try:
        r = requests.get(
            f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json",
            timeout=10, headers={"User-Agent": "caloriiibot/1.0"})
        d = r.json()
        if d.get("status") != 1:
            return None
        p = d["product"]; n = p.get("nutriments", {})
        return {"name": p.get("product_name") or "Без названия",
                "kcal": n.get("energy-kcal_100g", 0), "protein": n.get("proteins_100g", 0),
                "fat": n.get("fat_100g", 0), "carbs": n.get("carbohydrates_100g", 0)}
    except Exception as e:
        log.warning(f"OFF error: {e}"); return "error"

def off_search(name: str):
    try:
        r = requests.get("https://world.openfoodfacts.org/cgi/search.pl",
            params={"search_terms": name, "json": 1, "page_size": 1,
                    "fields": "product_name,nutriments"},
            timeout=10, headers={"User-Agent": "caloriiibot/1.0"})
        prods = r.json().get("products", [])
        if not prods: return None
        p = prods[0]; n = p.get("nutriments", {})
        return {"name": p.get("product_name") or name,
                "kcal": n.get("energy-kcal_100g", 0), "protein": n.get("proteins_100g", 0),
                "fat": n.get("fat_100g", 0), "carbs": n.get("carbohydrates_100g", 0)}
    except Exception: return None

# ── СПРАВОЧНИКИ ───────────────────────────────────────────────
BAD_ADDITIVES = {
    "е621": "глутамат натрия (усилитель вкуса)", "e621": "глутамат натрия",
    "е211": "бензоат натрия (консервант)",        "e211": "бензоат натрия",
    "е250": "нитрит натрия (консервант)",          "e250": "нитрит натрия",
    "е102": "тартразин (краситель-аллерген)",       "e102": "тартразин",
    "е951": "аспартам (подсластитель)",             "e951": "аспартам",
    "пальмовое масло": "пальмовое масло",
    "сахар": "добавленный сахар",
    "гидрогенизированн": "трансжиры",
    "маргарин": "маргарин (возможны трансжиры)",
}

MET = {"бег": 9.8, "ходьба": 3.5, "велосипед": 7.5, "плавание": 8.0,
       "силовая": 6.0, "йога": 3.0, "футбол": 8.0, "баскетбол": 7.5,
       "спринт": 12.0, "прыжки": 10.0}

FALLBACK_RECIPES = [
    {"name": "Курица с гречкой", "ing": "куриная грудка 150 г, гречка 80 г, овощи 150 г", "kcal": "~450 ккал"},
    {"name": "Омлет с овощами",  "ing": "3 яйца, помидор, шпинат", "kcal": "~320 ккал"},
    {"name": "Греческий салат с тунцом", "ing": "тунец 100 г, фета 40 г, овощи", "kcal": "~380 ккал"},
]

DAILY_TASKS = ["Съешь 3 разных овоща 🥦", "Пройди 8000 шагов 🚶",
               "Выпей 2 литра воды 💧", "Откажись от сладкого 🚫🍬",
               "Сделай 20 приседаний 🏋️"]

# ── FSM ───────────────────────────────────────────────────────
class St(StatesGroup):
    grams      = State()
    manual     = State()
    workout    = State()
    edit_grams = State()

router = Router()

# ── КЛАВИАТУРЫ ────────────────────────────────────────────────
def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
        for row in rows])

MAIN_KB = kb([
    [("📸 Распознать блюдо", "hint_photo"), ("🔍 Штрих-код", "hint_barcode")],
    [("✍️ Вручную", "manual"),              ("📋 Редактировать", "edit")],
    [("📅 Сегодня", "day"), ("📈 Неделя", "week"), ("🎯 Цель", "goal_hint")],
    [("💧 Вода +300 мл", "water_add"),      ("🔔 Напоминания", "water_remind")],
    [("🚶 Шаги", "hint_steps"),             ("🏋️ Тренировка", "workout")],
    [("📊 Инфографика", "chart"),           ("🍳 Рецепты", "recipes")],
    [("🎮 Задание дня", "task"),            ("📤 Экспорт CSV", "export")],
])

# ── УТИЛИТЫ ───────────────────────────────────────────────────
def meal_card(name, kcal, p, f, c, per="100 г"):
    return (f"🍽 <b>{name}</b>\n"
            f"Калорийность: <b>{kcal:.0f} ккал</b>/{per}\n"
            f"Б: {p:.1f} г · Ж: {f:.1f} г · У: {c:.1f} г")

def save_meal(uid, name, grams, kcal100, p100, f100, c100):
    k = grams / 100
    q("""INSERT INTO meals(user_id,date,meal_name,grams,calories,protein,fat,carbs)
         VALUES(?,?,?,?,?,?,?,?)""",
      (uid, today(), name, grams, round(kcal100*k,1),
       round(p100*k,1), round(f100*k,1), round(c100*k,1)))

def check_achievements(uid):
    days = [r["date"] for r in q(
        "SELECT DISTINCT date FROM meals WHERE user_id=? ORDER BY date DESC LIMIT 7", (uid,))]
    if len(days) == 7:
        d = [date.fromisoformat(x) for x in days]
        if all((d[i]-d[i+1]).days == 1 for i in range(6)):
            cur = q("INSERT OR IGNORE INTO achievements VALUES(?,?,datetime('now'))",
                    (uid, "iron7"))
            if cur.rowcount:
                return "🥉 Ачивка «Железная дисциплина» — 7 дней трекинга подряд!"
    return None

def day_stats(uid, d):
    r = q("""SELECT COALESCE(SUM(calories),0) k, COALESCE(SUM(protein),0) p,
             COALESCE(SUM(fat),0) f, COALESCE(SUM(carbs),0) c
             FROM meals WHERE user_id=? AND date=?""", (uid, d)).fetchone()
    w = q("SELECT COALESCE(SUM(ml),0) ml FROM water WHERE user_id=? AND date=?",
          (uid, d)).fetchone()["ml"]
    b = q("SELECT COALESCE(SUM(calories_burned),0) b FROM exercises WHERE user_id=? AND date=?",
          (uid, d)).fetchone()["b"]
    return r, w, b

# ── /start ────────────────────────────────────────────────────
@router.message(CommandStart())
async def start(m: Message):
    q("INSERT OR IGNORE INTO goals(user_id) VALUES(?)", (m.from_user.id,))
    await m.answer(
        "👋 Я <b>@caloriiibot</b> — считаю КБЖУ по фото!\n\n"
        "📸 Пришли фото блюда — распознаю и посчитаю.\n"
        "🔍 Пришли фото штрих-кода — найду продукт.\n"
        "🧪 Фото состава с подписью «состав» — найду E-добавки.\n"
        "🚶 Скрин шагомера с подписью «шаги» — посчитаю ккал.",
        reply_markup=MAIN_KB, parse_mode="HTML")

@router.message(Command("menu"))
async def cmd_menu(m: Message):
    await m.answer("Главное меню 👇", reply_markup=MAIN_KB)

# ── ФОТО В ЛС ─────────────────────────────────────────────────
@router.message(F.photo, F.chat.type == "private")
async def photo_private(m: Message, state: FSMContext, bot: Bot):
    cap = (m.caption or "").lower()
    buf = io.BytesIO()
    await bot.download(m.photo[-1], destination=buf)
    img = Image.open(buf)

    if "шаг" in cap:
        return await _steps(m, img)
    if "состав" in cap or "этикетка" in cap:
        return await _label(m, img)

    barcode = scan_barcode(img)
    if barcode:
        prod = off_product(barcode)
        if prod == "error":
            return await m.answer("⚠️ Open Food Facts недоступен, попробуй позже.")
        if prod is None:
            return await m.answer(
                f"Штрих-код <code>{barcode}</code> не найден.\n"
                "Добавь вручную: кнопка ✍️ Вручную.", parse_mode="HTML")
        await state.update_data(meal={**prod, "portion": 100})
        await state.set_state(St.grams)
        return await m.answer(
            "🍫 " + meal_card(prod["name"], prod["kcal"], prod["protein"],
                              prod["fat"], prod["carbs"]) +
            "\n\nСколько грамм съел? (число, «полпорции» или «стандарт»)",
            parse_mode="HTML")

    res = classify_food(img)
    if not res:
        return await m.answer(
            "⚠️ Модель не загружена (нет food_model.tflite).\n"
            "Распознай штрих-код или добавь вручную ✍️")
    cid, conf = res
    food = food_by_class(cid)
    if not food:
        return await m.answer("Блюдо не найдено в базе 😕")
    port = food["typical_portion"]
    meal = {"name": food["name"], "kcal": food["calories_per_100g"],
            "protein": food["protein"], "fat": food["fat"],
            "carbs": food["carbs"], "portion": port}
    await state.update_data(meal=meal)
    await state.set_state(St.grams)
    await m.answer(
        meal_card(food["name"], food["calories_per_100g"],
                  food["protein"], food["fat"], food["carbs"]) +
        f"\n(уверенность {conf*100:.0f}%)\n\n"
        f"Обычная порция <b>{port} г</b> = "
        f"<b>{food['calories_per_100g']*port/100:.0f} ккал</b>. Внести как {port} г?",
        parse_mode="HTML",
        reply_markup=kb([[("✅ Да", f"portion_{port}"),
                          ("✍️ Ввести вручную", "portion_manual")]]))

@router.callback_query(F.data.startswith("portion_"))
async def portion_cb(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    meal = data.get("meal")
    if not meal:
        return await c.answer("Сессия истекла, пришли фото снова")
    if c.data == "portion_manual":
        await c.message.answer("Введи граммы числом:")
        return await c.answer()
    grams = float(c.data.split("_")[1])
    save_meal(c.from_user.id, meal["name"], grams,
              meal["kcal"], meal["protein"], meal["fat"], meal["carbs"])
    await state.clear()
    await c.message.answer(
        f"✅ {meal['name']}, {grams:.0f} г — {meal['kcal']*grams/100:.0f} ккал")
    ach = check_achievements(c.from_user.id)
    if ach: await c.message.answer(ach)
    await c.answer()

@router.message(St.grams)
async def grams_input(m: Message, state: FSMContext):
    meal = (await state.get_data())["meal"]
    t = m.text.lower().strip()
    port = meal.get("portion", 100)
    if "полпорц" in t:    grams = port / 2
    elif "стандарт" in t: grams = port
    else:
        try: grams = float(re.sub(r"[^\d.]", "", t))
        except ValueError: return await m.answer("Введи число, «полпорции» или «стандарт».")
    save_meal(m.from_user.id, meal["name"], grams,
              meal["kcal"], meal["protein"], meal["fat"], meal["carbs"])
    await state.clear()
    await m.answer(f"✅ {meal['name']}, {grams:.0f} г — {meal['kcal']*grams/100:.0f} ккал")
    ach = check_achievements(m.from_user.id)
    if ach: await m.answer(ach)

# ── OCR ЭТИКЕТКИ ──────────────────────────────────────────────
async def _label(m: Message, img: Image.Image):
    if not pytesseract:
        return await m.answer("OCR недоступен (tesseract не установлен).")
    text = pytesseract.image_to_string(img, lang="rus+eng").lower()
    found = sorted({desc for key, desc in BAD_ADDITIVES.items() if key in text})
    if found:
        await m.answer("⚠️ Найдены: " + ", ".join(found) +
                       ".\nВердикт: скорее вредно, чем полезно.")
    else:
        await m.answer("✅ Явно вредных добавок не найдено. Вердикт: скорее ок 👍")

# ── OCR ШАГОМЕРА ──────────────────────────────────────────────
async def _steps(m: Message, img: Image.Image):
    if not pytesseract:
        return await m.answer("OCR недоступен (tesseract не установлен).")
    text = pytesseract.image_to_string(img)
    nums = [int(re.sub(r"[ ,.]", "", n)) for n in re.findall(r"\d[\d ,\.]{2,}", text)]
    steps = max((n for n in nums if 100 <= n <= 100_000), default=None)
    if not steps:
        return await m.answer("Не разглядел шаги 😕 Пришли скрин почётче.")
    kcal = round(steps * 0.04)
    q("INSERT INTO exercises(user_id,date,kind,detail,calories_burned) VALUES(?,?,?,?,?)",
      (m.from_user.id, today(), "steps", f"{steps} шагов", kcal))
    await m.answer(f"📱 {steps:,} шагов → −{kcal} ккал сожжено. Записано!".replace(",", " "))

# ── ГРУППЫ ────────────────────────────────────────────────────
@router.message(F.photo, F.chat.type.in_({"group", "supergroup"}))
async def photo_group(m: Message, bot: Bot):
    if f"@{BOT_USERNAME}" not in (m.caption or "").lower():
        return
    buf = io.BytesIO()
    await bot.download(m.photo[-1], destination=buf)
    img = Image.open(buf)
    barcode = scan_barcode(img)
    if barcode:
        prod = off_product(barcode)
        if prod and prod != "error":
            return await m.reply(f"🍫 {prod['name']}: {prod['kcal']:.0f} ккал/100 г")
        return await m.reply("Продукт не найден.")
    res = classify_food(img)
    if res:
        food = food_by_class(res[0])
        if food:
            return await m.reply(f"🍽 {food['name']}: {food['calories_per_100g']:.0f} ккал/100 г")
    await m.reply("Не смог распознать 😕")

# ── ДНЕВНИК: сегодня / неделя / цель ─────────────────────────
@router.callback_query(F.data == "day")
async def cb_day(c: CallbackQuery):
    uid = c.from_user.id
    r, w, burned = day_stats(uid, today())
    goal = (q("SELECT daily_calories FROM goals WHERE user_id=?", (uid,)).fetchone()
            or {"daily_calories": 2000})["daily_calories"]
    pct  = min(int(r["k"] / goal * 10), 10)
    bar  = "🟩" * pct + "⬜" * (10 - pct)
    await c.message.answer(
        f"📅 <b>Сегодня</b>\n"
        f"Калории: <b>{r['k']:.0f} / {goal}</b>\n{bar}\n"
        f"Б: {r['p']:.0f} г · Ж: {r['f']:.0f} г · У: {r['c']:.0f} г\n"
        f"💧 Вода: {w} мл\n🔥 Активность: −{burned:.0f} ккал",
        parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data == "week")
async def cb_week(c: CallbackQuery):
    uid = c.from_user.id
    lines, tot = [], 0
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        r, _, _ = day_stats(uid, d)
        tot += r["k"]
        stars = "★" * min(int(r["k"] / 400), 8)
        lines.append(f"{d[5:]} {stars or '·'} {r['k']:.0f}")
    await c.message.answer(
        "📈 <b>Неделя</b> (ккал/день):\n<code>" +
        "\n".join(lines) + f"\n</code>Среднее: <b>{tot/7:.0f} ккал/день</b>",
        parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data == "goal_hint")
async def cb_goal_hint(c: CallbackQuery):
    await c.message.answer("Установи цель: <code>/goal 1800</code>", parse_mode="HTML")
    await c.answer()

@router.message(Command("goal"))
async def cmd_goal(m: Message):
    try:
        g = int(m.text.split()[1])
        assert 800 <= g <= 6000
    except (IndexError, ValueError, AssertionError):
        return await m.answer("Формат: /goal 2000 (800–6000)")
    q("INSERT INTO goals(user_id,daily_calories) VALUES(?,?) "
      "ON CONFLICT(user_id) DO UPDATE SET daily_calories=?", (m.from_user.id, g, g))
    await m.answer(f"🎯 Цель: {g} ккал/день")

# ── РЕДАКТИРОВАНИЕ ────────────────────────────────────────────
@router.callback_query(F.data == "edit")
async def cb_edit(c: CallbackQuery):
    rows = q("""SELECT id,meal_name,grams,calories FROM meals
                WHERE user_id=? ORDER BY id DESC LIMIT 5""", (c.from_user.id,)).fetchall()
    if not rows:
        await c.message.answer("Дневник пуст.")
        return await c.answer()
    for r in rows:
        await c.message.answer(
            f"{r['meal_name']} — {r['grams']:.0f} г, {r['calories']:.0f} ккал",
            reply_markup=kb([[("🗑 Удалить", f"del_{r['id']}"),
                              ("✏️ Граммы", f"chg_{r['id']}")]]))
    await c.answer()

@router.callback_query(F.data.startswith("del_"))
async def cb_del(c: CallbackQuery):
    q("DELETE FROM meals WHERE id=? AND user_id=?",
      (int(c.data[4:]), c.from_user.id))
    await c.message.edit_text("🗑 Удалено")
    await c.answer()

@router.callback_query(F.data.startswith("chg_"))
async def cb_chg(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.edit_grams)
    await state.update_data(meal_id=int(c.data[4:]))
    await c.message.answer("Введи новые граммы:")
    await c.answer()

@router.message(St.edit_grams)
async def edit_grams(m: Message, state: FSMContext):
    try: grams = float(m.text)
    except ValueError: return await m.answer("Число, пожалуйста.")
    mid = (await state.get_data())["meal_id"]
    r = q("SELECT * FROM meals WHERE id=? AND user_id=?",
          (mid, m.from_user.id)).fetchone()
    if r and r["grams"]:
        k = grams / r["grams"]
        q("UPDATE meals SET grams=?,calories=?,protein=?,fat=?,carbs=? WHERE id=?",
          (grams, r["calories"]*k, r["protein"]*k, r["fat"]*k, r["carbs"]*k, mid))
        await m.answer(f"✏️ Обновил: {grams:.0f} г")
    await state.clear()

# ── РУЧНОЙ ВВОД ───────────────────────────────────────────────
@router.callback_query(F.data == "manual")
async def cb_manual(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.manual)
    await c.message.answer(
        "Формат: <code>название граммы</code> — найду в Open Food Facts\n"
        "или полно: <code>название граммы ккал б ж у</code> (на 100 г)",
        parse_mode="HTML")
    await c.answer()

@router.message(St.manual)
async def manual_input(m: Message, state: FSMContext):
    try:
        parts = m.text.split()
        if len(parts) >= 6:
            nums = list(map(float, parts[-5:]))
            name = " ".join(parts[:-5])
            grams, kcal, p, f_, c_ = nums
            save_meal(m.from_user.id, name, grams, kcal, p, f_, c_)
            await m.answer(f"✅ Записал: {name}, {grams:.0f} г")
        else:
            grams = float(parts[-1])
            name  = " ".join(parts[:-1])
            prod  = off_search(name)
            if not prod:
                return await m.answer("Не нашёл в Open Food Facts.\n"
                                      "Введи полно: название г ккал б ж у")
            save_meal(m.from_user.id, prod["name"], grams,
                      prod["kcal"], prod["protein"], prod["fat"], prod["carbs"])
            await m.answer(f"✅ {prod['name']}, {grams:.0f} г "
                           f"({prod['kcal']*grams/100:.0f} ккал)")
        await state.clear()
    except (ValueError, IndexError):
        await m.answer("Формат: <code>гречка 150</code>", parse_mode="HTML")

# ── /compare ─────────────────────────────────────────────────
@router.message(Command("compare"))
async def cmd_compare(m: Message):
    txt = m.text.removeprefix("/compare").strip()
    if " vs " not in txt:
        return await m.answer("Формат: /compare творог vs йогурт")
    a, b = [s.strip() for s in txt.split(" vs ", 1)]
    pa, pb = off_search(a), off_search(b)
    if not pa or not pb:
        return await m.answer("Один из продуктов не найден.")
    def row(p): return f"{p['kcal']:.0f} | {p['protein']:.1f} | {p['fat']:.1f} | {p['carbs']:.1f}"
    better = pa if pa["kcal"] < pb["kcal"] else pb
    pking  = pa if pa["protein"] > pb["protein"] else pb
    await m.answer(
        f"📊 <b>Сравнение (на 100 г)</b>\n<code>"
        f"             ккал | Б  | Ж  | У\n"
        f"{pa['name'][:13]:13} {row(pa)}\n"
        f"{pb['name'][:13]:13} {row(pb)}</code>\n\n"
        f"Для похудения: <b>{better['name']}</b>\n"
        f"Для мышц: <b>{pking['name']}</b>", parse_mode="HTML")

# ── /dish ─────────────────────────────────────────────────────
@router.message(Command("dish"))
async def cmd_dish(m: Message):
    txt = m.text.removeprefix("/dish").strip()
    if not txt:
        return await m.answer("Формат: /dish курица, гречка, огурец")
    items = [s.strip() for s in txt.split(",")][:5]
    parts, tot = [], {"k":0,"p":0,"f":0,"c":0}
    default_g = [150, 100, 100, 80, 80]
    for i, it in enumerate(items):
        prod = off_search(it)
        if not prod: parts.append(f"• {it}: не найден"); continue
        g = default_g[i]; k = g/100
        tot["k"] += prod["kcal"]*k; tot["p"] += prod["protein"]*k
        tot["f"] += prod["fat"]*k;  tot["c"] += prod["carbs"]*k
        parts.append(f"• {prod['name']} — {g} г ({prod['kcal']*k:.0f} ккал)")
    await m.answer("🧑‍🍳 <b>Блюдо:</b>\n" + "\n".join(parts) +
                   f"\n\nИтого: <b>{tot['k']:.0f} ккал</b>, "
                   f"Б {tot['p']:.0f} / Ж {tot['f']:.0f} / У {tot['c']:.0f}",
                   parse_mode="HTML")

# ── Рецепты ───────────────────────────────────────────────────
@router.callback_query(F.data == "recipes")
async def cb_recipes(c: CallbackQuery):
    await c.message.answer("Формат: /recipe курица рис")
    await c.answer()

@router.message(Command("recipe"))
async def cmd_recipe(m: Message):
    ing = m.text.removeprefix("/recipe").strip()
    if SPOONACULAR and ing:
        try:
            r = requests.get("https://api.spoonacular.com/recipes/findByIngredients",
                             params={"ingredients": ing, "number": 1,
                                     "apiKey": SPOONACULAR}, timeout=10).json()
            if r:
                rec = r[0]
                return await m.answer(f"📖 <b>{rec['title']}</b>\n"
                                      f"https://spoonacular.com/recipes/-{rec['id']}",
                                      parse_mode="HTML")
        except Exception:
            pass
    rec = random.choice(FALLBACK_RECIPES)
    await m.answer(f"📖 <b>{rec['name']}</b>\n{rec['ing']}\n{rec['kcal']}",
                   parse_mode="HTML")

# ── Тренировка ────────────────────────────────────────────────
@router.callback_query(F.data == "workout")
async def cb_workout(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.workout)
    await c.message.answer(
        "Формат: <code>вид минуты вес_кг</code>\n"
        "Пример: <code>бег 30 70</code>\n"
        "Виды: " + ", ".join(MET), parse_mode="HTML")
    await c.answer()

@router.message(St.workout)
async def workout_input(m: Message, state: FSMContext):
    try:
        kind, mins, weight = m.text.lower().split()
        mins, weight = float(mins), float(weight)
        met = MET[kind]
    except (ValueError, KeyError):
        return await m.answer("Формат: бег 30 70")
    kcal = round(met * weight * mins / 60)
    q("INSERT INTO exercises(user_id,date,kind,detail,calories_burned) VALUES(?,?,?,?,?)",
      (m.from_user.id, today(), "workout", f"{kind} {mins:.0f} мин", kcal))
    await state.clear()
    await m.answer(f"🏋️ {kind.capitalize()} {mins:.0f} мин → −{kcal} ккал. Записал!")

# ── Вода ──────────────────────────────────────────────────────
@router.callback_query(F.data == "water_add")
async def cb_water(c: CallbackQuery):
    q("INSERT INTO water(user_id,date,ml) VALUES(?,?,300)", (c.from_user.id, today()))
    total = q("SELECT SUM(ml) s FROM water WHERE user_id=? AND date=?",
              (c.from_user.id, today())).fetchone()["s"]
    await c.answer(f"💧 +300 мл (всего {total} мл сегодня)", show_alert=True)

@router.callback_query(F.data == "water_remind")
async def cb_remind(c: CallbackQuery):
    cur = q("SELECT water_reminders FROM goals WHERE user_id=?",
            (c.from_user.id,)).fetchone()
    new = 0 if (cur and cur["water_reminders"]) else 1
    q("INSERT INTO goals(user_id,water_reminders) VALUES(?,?) "
      "ON CONFLICT(user_id) DO UPDATE SET water_reminders=?",
      (c.from_user.id, new, new))
    await c.answer("🔔 Напоминания каждые 2 ч включены" if new
                   else "🔕 Напоминания выключены", show_alert=True)

async def water_reminder_loop(bot: Bot):
    while True:
        await asyncio.sleep(2 * 3600)
        for r in q("SELECT user_id FROM goals WHERE water_reminders=1"):
            try: await bot.send_message(r["user_id"], "💧 Время выпить воды!")
            except Exception: pass

# ── Инфографика ───────────────────────────────────────────────
@router.callback_query(F.data == "chart")
async def cb_chart(c: CallbackQuery):
    uid = c.from_user.id
    days, vals = [], []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        r, _, _ = day_stats(uid, d.isoformat())
        days.append(d.strftime("%d.%m")); vals.append(r["k"])
    goal = (q("SELECT daily_calories FROM goals WHERE user_id=?", (uid,)).fetchone()
            or {"daily_calories": 2000})["daily_calories"]
    W, H, pad = 800, 400, 60
    img = Image.new("RGB", (W, H), "#1a1a2e")
    dr = ImageDraw.Draw(img)
    try:    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except: font = ImageFont.load_default()
    mx = max(max(vals, default=1), goal, 1)
    bw = (W - 2*pad) / 7
    gy = H - pad - (goal/mx)*(H-2*pad)
    dr.line([(pad, gy), (W-pad, gy)], fill="#e94560", width=2)
    dr.text((W-pad-110, gy-25), f"цель {goal}", fill="#e94560", font=font)
    for i, v in enumerate(vals):
        x = pad + i*bw + 8
        h = (v/mx)*(H-2*pad) if mx else 0
        color = "#0f9b58" if v <= goal else "#e94560"
        dr.rectangle([x, H-pad-h, x+bw-16, H-pad], fill=color)
        dr.text((x, H-pad+8), days[i], fill="white", font=font)
        if v: dr.text((x, H-pad-h-25), f"{v:.0f}", fill="white", font=font)
    dr.text((pad, 15), "📊 Калории за неделю", fill="white", font=font)
    out = io.BytesIO()
    img.save(out, "PNG")
    await c.message.answer_photo(
        BufferedInputFile(out.getvalue(), "progress.png"),
        caption="📈 Прогресс за неделю")
    await c.answer()

# ── Задание дня ───────────────────────────────────────────────
@router.callback_query(F.data == "task")
async def cb_task(c: CallbackQuery):
    random.seed(f"{c.from_user.id}{today()}")
    task = random.choice(DAILY_TASKS)
    random.seed()
    await c.message.answer(f"🎮 Задание дня: <b>{task}</b>", parse_mode="HTML")
    await c.answer()

# ── Экспорт CSV ───────────────────────────────────────────────
@router.callback_query(F.data == "export")
async def cb_export(c: CallbackQuery):
    rows = q("SELECT date,meal_name,grams,calories,protein,fat,carbs FROM meals "
             "WHERE user_id=? ORDER BY date", (c.from_user.id,)).fetchall()
    csv = "date;meal;grams;kcal;protein;fat;carbs\n" + "\n".join(
        f"{r['date']};{r['meal_name']};{r['grams']};{r['calories']};"
        f"{r['protein']};{r['fat']};{r['carbs']}" for r in rows)
    await c.message.answer_document(
        BufferedInputFile(csv.encode("utf-8-sig"), "diary.csv"),
        caption="📤 Дневник в CSV (открой в Excel или Google Sheets)")
    await c.answer()

# ── Хинты ─────────────────────────────────────────────────────
@router.callback_query(F.data.in_({"hint_photo","hint_barcode","hint_steps"}))
async def cb_hints(c: CallbackQuery):
    hints = {"hint_photo":   "Просто пришли фото блюда 📸",
             "hint_barcode": "Пришли фото штрих-кода 🔍",
             "hint_steps":   "Пришли скриншот шагомера с подписью «шаги» 🚶"}
    await c.answer(hints[c.data], show_alert=True)

@router.message(Command("challenge"), F.chat.type.in_({"group","supergroup"}))
async def cmd_challenge(m: Message):
    await m.answer("🏆 Шлите скрины шагомеров с подписью «шаги @caloriiibot». "
                   "Турнирная таблица — в разработке.")

# ── MAIN ──────────────────────────────────────────────────────
async def main():
    from aiogram.client.default import DefaultBotProperties
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    asyncio.create_task(water_reminder_loop(bot))
    log.info("@caloriiibot запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
