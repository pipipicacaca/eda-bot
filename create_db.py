# ============================================================
# create_db.py — создаёт food.db для @caloriiibot
# Таблицы: foods (БЖУ 101 блюда Food-101), meals, water,
# exercises, goals, achievements
# Запуск: python3 create_db.py
# ============================================================
import sqlite3

# class_id соответствует порядку строк в labels.txt (алфавитный порядок Food-101)
# (en_name, ru_name, kcal/100г, белки, жиры, углеводы, типичная порция в граммах)
FOODS = [
    ("apple_pie", "Яблочный пирог", 237, 2.4, 11.0, 34.0, 150),
    ("baby_back_ribs", "Свиные рёбрышки BBQ", 290, 24.0, 21.0, 2.0, 250),
    ("baklava", "Пахлава", 430, 6.0, 23.0, 52.0, 100),
    ("beef_carpaccio", "Карпаччо из говядины", 150, 22.0, 6.5, 1.0, 120),
    ("beef_tartare", "Тартар из говядины", 180, 20.0, 10.0, 2.0, 150),
    ("beet_salad", "Свекольный салат", 90, 2.5, 4.5, 11.0, 200),
    ("beignets", "Бенье (пончики)", 350, 6.0, 17.0, 44.0, 120),
    ("bibimbap", "Бибимбап", 130, 7.0, 4.5, 16.0, 400),
    ("bread_pudding", "Хлебный пудинг", 230, 5.5, 9.0, 32.0, 180),
    ("breakfast_burrito", "Завтрак-буррито", 210, 10.0, 10.0, 20.0, 250),
    ("bruschetta", "Брускетта", 190, 5.0, 7.0, 27.0, 120),
    ("caesar_salad", "Салат Цезарь", 180, 8.0, 13.0, 8.0, 250),
    ("cannoli", "Канноли", 370, 7.0, 21.0, 38.0, 90),
    ("caprese_salad", "Салат Капрезе", 170, 9.0, 13.0, 4.0, 200),
    ("carrot_cake", "Морковный торт", 410, 4.5, 23.0, 47.0, 120),
    ("ceviche", "Севиче", 100, 16.0, 2.0, 5.0, 200),
    ("cheesecake", "Чизкейк", 320, 6.0, 22.0, 26.0, 130),
    ("cheese_plate", "Сырная тарелка", 380, 23.0, 31.0, 2.5, 150),
    ("chicken_curry", "Курица карри", 140, 12.0, 8.0, 5.0, 300),
    ("chicken_quesadilla", "Кесадилья с курицей", 260, 14.0, 13.0, 22.0, 220),
    ("chicken_wings", "Куриные крылышки", 290, 27.0, 19.0, 1.0, 200),
    ("chocolate_cake", "Шоколадный торт", 380, 5.0, 18.0, 51.0, 120),
    ("chocolate_mousse", "Шоколадный мусс", 250, 4.5, 16.0, 22.0, 120),
    ("churros", "Чуррос", 380, 5.0, 20.0, 45.0, 100),
    ("clam_chowder", "Клэм-чаудер (суп)", 95, 5.0, 4.5, 9.0, 300),
    ("club_sandwich", "Клаб-сэндвич", 240, 13.0, 11.0, 23.0, 250),
    ("crab_cakes", "Крабовые котлеты", 190, 14.0, 10.0, 10.0, 150),
    ("creme_brulee", "Крем-брюле", 290, 4.5, 22.0, 19.0, 130),
    ("croque_madame", "Крок-мадам", 270, 14.0, 16.0, 17.0, 220),
    ("cup_cakes", "Капкейки", 400, 4.0, 18.0, 56.0, 80),
    ("deviled_eggs", "Фаршированные яйца", 200, 11.0, 16.0, 1.5, 100),
    ("donuts", "Пончики", 420, 5.0, 23.0, 49.0, 75),
    ("dumplings", "Пельмени/дамплинги", 220, 9.0, 9.0, 26.0, 250),
    ("edamame", "Эдамаме", 120, 11.0, 5.0, 9.0, 150),
    ("eggs_benedict", "Яйца Бенедикт", 250, 12.0, 18.0, 11.0, 220),
    ("escargots", "Эскарго (улитки)", 180, 13.0, 13.0, 3.0, 100),
    ("falafel", "Фалафель", 330, 13.0, 18.0, 31.0, 150),
    ("filet_mignon", "Филе-миньон", 250, 26.0, 16.0, 0.0, 200),
    ("fish_and_chips", "Фиш-энд-чипс", 270, 12.0, 15.0, 23.0, 300),
    ("foie_gras", "Фуа-гра", 460, 11.0, 44.0, 5.0, 70),
    ("french_fries", "Картофель фри", 310, 3.5, 15.0, 41.0, 150),
    ("french_onion_soup", "Луковый суп", 80, 4.0, 4.0, 8.0, 300),
    ("french_toast", "Французские тосты", 230, 8.0, 10.0, 27.0, 150),
    ("fried_calamari", "Жареные кальмары", 200, 13.0, 9.0, 17.0, 180),
    ("fried_rice", "Жареный рис", 165, 5.0, 5.0, 25.0, 300),
    ("frozen_yogurt", "Замороженный йогурт", 130, 4.0, 3.5, 21.0, 150),
    ("garlic_bread", "Чесночный хлеб", 350, 8.0, 15.0, 45.0, 100),
    ("gnocchi", "Ньокки", 180, 5.0, 4.0, 31.0, 250),
    ("greek_salad", "Греческий салат", 110, 4.0, 8.0, 6.0, 250),
    ("grilled_cheese_sandwich", "Сэндвич с сыром гриль", 330, 12.0, 19.0, 28.0, 150),
    ("grilled_salmon", "Лосось на гриле", 210, 22.0, 13.0, 0.0, 180),
    ("guacamole", "Гуакамоле", 160, 2.0, 14.0, 9.0, 100),
    ("gyoza", "Гёдза", 200, 8.0, 8.0, 24.0, 180),
    ("hamburger", "Гамбургер", 260, 13.0, 12.0, 25.0, 250),
    ("hot_and_sour_soup", "Кисло-острый суп", 50, 3.5, 2.0, 5.0, 300),
    ("hot_dog", "Хот-дог", 290, 10.0, 18.0, 23.0, 180),
    ("huevos_rancheros", "Уэвос ранчерос", 160, 8.0, 9.0, 12.0, 300),
    ("hummus", "Хумус", 240, 8.0, 14.0, 20.0, 100),
    ("ice_cream", "Мороженое", 210, 3.5, 11.0, 24.0, 100),
    ("lasagna", "Лазанья", 165, 9.0, 8.0, 14.0, 300),
    ("lobster_bisque", "Биск из лобстера", 90, 5.0, 5.0, 6.0, 300),
    ("lobster_roll_sandwich", "Ролл с лобстером", 220, 12.0, 11.0, 18.0, 200),
    ("macaroni_and_cheese", "Макароны с сыром", 220, 9.0, 10.0, 24.0, 300),
    ("macarons", "Макаруны", 430, 7.0, 20.0, 56.0, 60),
    ("miso_soup", "Мисо-суп", 40, 3.0, 1.5, 4.0, 300),
    ("mussels", "Мидии", 110, 15.0, 3.0, 5.0, 250),
    ("nachos", "Начос", 320, 9.0, 18.0, 30.0, 200),
    ("omelette", "Омлет", 155, 11.0, 12.0, 1.0, 200),
    ("onion_rings", "Луковые кольца", 360, 4.5, 19.0, 42.0, 130),
    ("oysters", "Устрицы", 70, 8.0, 2.5, 4.0, 150),
    ("pad_thai", "Пад-тай", 180, 9.0, 7.0, 21.0, 350),
    ("paella", "Паэлья", 160, 10.0, 5.0, 19.0, 350),
    ("pancakes", "Блины/панкейки", 230, 6.0, 9.0, 31.0, 180),
    ("panna_cotta", "Панна-котта", 230, 3.5, 17.0, 16.0, 130),
    ("peking_duck", "Утка по-пекински", 340, 19.0, 28.0, 3.0, 200),
    ("pho", "Фо-бо", 60, 5.0, 1.5, 7.0, 450),
    ("pizza", "Пицца", 265, 11.0, 10.0, 33.0, 300),
    ("pork_chop", "Свиная отбивная", 230, 26.0, 14.0, 0.0, 200),
    ("poutine", "Путин (картофель с соусом)", 240, 7.0, 13.0, 24.0, 300),
    ("prime_rib", "Прайм-риб (ростбиф)", 310, 22.0, 25.0, 0.0, 250),
    ("pulled_pork_sandwich", "Сэндвич с рваной свининой", 220, 14.0, 8.0, 23.0, 250),
    ("ramen", "Рамен", 90, 5.0, 3.0, 11.0, 450),
    ("ravioli", "Равиоли", 190, 8.0, 6.0, 26.0, 250),
    ("red_velvet_cake", "Торт Красный бархат", 390, 4.0, 19.0, 52.0, 120),
    ("risotto", "Ризотто", 160, 5.0, 5.0, 24.0, 300),
    ("samosa", "Самоса", 300, 6.0, 15.0, 35.0, 120),
    ("sashimi", "Сашими", 130, 22.0, 4.5, 0.5, 150),
    ("scallops", "Гребешки", 110, 17.0, 1.5, 6.0, 150),
    ("seaweed_salad", "Салат из водорослей", 70, 1.5, 3.5, 9.0, 120),
    ("shrimp_and_grits", "Креветки с гритс", 150, 10.0, 7.0, 12.0, 300),
    ("spaghetti_bolognese", "Спагетти болоньезе", 160, 8.0, 6.0, 19.0, 350),
    ("spaghetti_carbonara", "Паста карбонара", 280, 11.0, 13.0, 29.0, 300),
    ("spring_rolls", "Спринг-роллы", 150, 4.5, 5.0, 22.0, 150),
    ("steak", "Стейк", 270, 25.0, 19.0, 0.0, 250),
    ("strawberry_shortcake", "Клубничный торт", 300, 4.0, 14.0, 40.0, 130),
    ("sushi", "Суши", 150, 6.0, 2.5, 27.0, 200),
    ("tacos", "Тако", 220, 11.0, 11.0, 19.0, 200),
    ("takoyaki", "Такояки", 180, 8.0, 7.0, 21.0, 150),
    ("tiramisu", "Тирамису", 290, 5.0, 19.0, 25.0, 130),
    ("tuna_tartare", "Тартар из тунца", 140, 20.0, 5.5, 2.0, 150),
    ("waffles", "Вафли", 290, 7.0, 13.0, 37.0, 130),
]

assert len(FOODS) == 101, f"Должно быть 101 блюдо, сейчас {len(FOODS)}"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS foods (
    class_id INTEGER PRIMARY KEY,
    en_name TEXT UNIQUE,
    name TEXT,
    calories_per_100g REAL,
    protein REAL,
    fat REAL,
    carbs REAL,
    typical_portion INTEGER DEFAULT 100
);

CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,              -- YYYY-MM-DD
    meal_name TEXT,
    grams REAL,
    calories REAL,
    protein REAL,
    fat REAL,
    carbs REAL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_meals_user_date ON meals(user_id, date);

CREATE TABLE IF NOT EXISTS water (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    ml INTEGER
);
CREATE INDEX IF NOT EXISTS idx_water_user_date ON water(user_id, date);

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    kind TEXT,                       -- 'steps' / 'workout'
    detail TEXT,
    calories_burned REAL
);

CREATE TABLE IF NOT EXISTS goals (
    user_id INTEGER PRIMARY KEY,
    daily_calories INTEGER DEFAULT 2000,
    water_reminders INTEGER DEFAULT 0   -- 1 = включены
);

CREATE TABLE IF NOT EXISTS achievements (
    user_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    earned_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, code)
);
"""

def main():
    con = sqlite3.connect("food.db")
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT OR REPLACE INTO foods VALUES (?,?,?,?,?,?,?,?)",
        [(i, en, ru, k, p, f, c, port) for i, (en, ru, k, p, f, c, port) in enumerate(FOODS)],
    )
    con.commit()
    con.close()
    print("food.db создан: 101 блюдо + все таблицы")

if __name__ == "__main__":
    main()
