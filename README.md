# @caloriiibot — инструкция по запуску (бюджет 0₽)

## Файлы проекта
| Файл | Что это |
|---|---|
| `colab_train.py` | Код для Google Colab — обучает модель, выдаёт `food_model.tflite` + `labels.txt` |
| `create_db.py` | Создаёт `food.db` (БЖУ 101 блюда + все таблицы) |
| `food.db` | Уже готовая база (можно не запускать create_db.py) |
| `bot.py` | Полный код бота (aiogram 3) |
| `requirements.txt` | Зависимости |

## Шаг 1. Регистрация бота
1. Открой **@BotFather** → `/newbot` → имя → username `caloriiibot` (или свой).
2. Скопируй токен.
3. `/setprivacy` → выбери бота → **Disable** (чтобы бот видел фото в группах).

## Шаг 2. Обучение модели (Google Colab, ~40–60 мин на T4)
1. colab.research.google.com → новый блокнот → Runtime → Change runtime type → **T4 GPU**.
2. Скопируй ячейки из `colab_train.py` (разделены маркерами `# %% [ячейка N]`).
3. Запусти всё по порядку. В конце скачаются `food_model.tflite` (~9 МБ) и `labels.txt`.

Без модели бот тоже работает: штрих-коды, дневник, вода и пр. — распознавание блюд просто отключится.

## Шаг 3. PythonAnywhere (Free)
1. Зарегистрируйся на pythonanywhere.com (Free tier).
2. Загрузи через вкладку **Files**: `bot.py`, `create_db.py`, `food.db`, `food_model.tflite`, `labels.txt`, `requirements.txt`.
3. Открой **Bash console**:
```bash
# системные библиотеки zbar и tesseract на PythonAnywhere уже установлены.
# Если нет (другой хостинг): sudo apt install libzbar0 tesseract-ocr tesseract-ocr-rus
pip3 install --user aiogram requests numpy Pillow pyzbar pytesseract
pip3 install --user tflite-runtime   # если не встанет — модельная часть отключится gracefully
export BOT_TOKEN="123456:ABC..."     # твой токен
python3 bot.py
```

⚠️ Важно про Free-тариф PythonAnywhere: консольные процессы там периодически убиваются, а **Always-on tasks доступны только на платном тарифе**. UptimeRobot помогает только веб-приложениям (Flask и т.п.), а не polling-боту. Реально бесплатные варианты 24/7:
- **Hugging Face Spaces** (Docker Space, см. ниже) + UptimeRobot,
- или твой привычный **Railway** (trial-кредитов хватает на лёгкого бота).

## Шаг 3-альтернатива. Hugging Face Spaces (бесплатно, 24/7)
1. huggingface.co → New Space → SDK: **Docker** → Blank.
2. Загрузи все файлы + такой `Dockerfile`:
```dockerfile
FROM python:3.10-slim
RUN apt-get update && apt-get install -y libzbar0 tesseract-ocr tesseract-ocr-rus && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt flask
# мини-веб-сервер для keep-alive (UptimeRobot пингует порт 7860)
CMD python3 -c "import threading,subprocess;from flask import Flask;app=Flask('k');app.route('/')(lambda: 'ok');threading.Thread(target=lambda: subprocess.run(['python3','bot.py'])).start();app.run('0.0.0.0',7860)"
```
3. В Settings → Variables добавь `BOT_TOKEN`.
4. **UptimeRobot**: uptimerobot.com → Add Monitor → HTTP(s) → URL твоего Space (`https://username-spacename.hf.space`) → интервал 5 минут. Space не уснёт.

## Шаг 4. Проверка
- Пришли боту фото блюда → название + КБЖУ + «Внести как N г?».
- Фото штрих-кода → продукт из Open Food Facts.
- Фото состава с подписью «состав» → анализ E-добавок.
- Скрин шагомера с подписью «шаги» → сожжённые калории.
- `/menu`, `/goal 1800`, `/compare творог vs йогурт`, `/dish курица, гречка`, `/recipe курица`.
- В группе: фото с подписью `@caloriiibot` → краткий ответ с калориями.

## Переменные
| Переменная | Обязательно | Где взять |
|---|---|---|
| `BOT_TOKEN` | да | @BotFather |
| `SPOONACULAR_KEY` | нет | spoonacular.com/food-api (150 запросов/день бесплатно); без ключа — встроенные рецепты |

## Что упрощено / заглушки
- Турнирная таблица челленджей в группах — заглушка (`/challenge`).
- Экспорт — CSV-файл (открывается в Sheets/Excel); прямой API Google Sheets/Notion — «в разработке».
- Видео-рецепты (YouTube API) — не включены, рецепты текстовые.
- Партнёрские рекомендации — не включены (требуют аналитики покупок).
