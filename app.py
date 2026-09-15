import asyncio
import os
import random
import sqlite3
from aiogram import Bot, Dispatcher, types
import aiohttp
import wikipediaapi
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from urllib.parse import quote
import base64

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

wiki = wikipediaapi.Wikipedia(
    user_agent='QBot/1.0 (https://t.me/AlpfyHelper_bot)',
    language='ru'
)

# ========== БАЗА ДАННЫХ (ПОСТОЯННАЯ ПАМЯТЬ) ==========
DB_PATH = "qbot_memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

def save_message(user_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO memory (user_id, role, content) VALUES (?, ?, ?)",
              (user_id, role, content))
    conn.commit()
    conn.close()

def get_history(user_id, limit=30):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT role, content FROM memory
                 WHERE user_id = ?
                 ORDER BY id DESC LIMIT ?""", (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

def clear_history(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM memory WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

init_db()
# ====================================================

TIME_TRIGGERS = ["который час", "сколько времени", "текущее время", "время сейчас", "время в бишкеке", "сколько сейчас времени", "время"]
WIKI_TRIGGERS = ["кто такой", "кто такая", "кто такое", "что такое", "что за", "расскажи про", "расскажи о", "расскажи", "информация о", "информация про", "информация", "найди про", "найди о", "найди", "википедия", "вики", "статья", "объясни", "объясни про", "определение"]
WEATHER_TRIGGERS = ["погода", "погоду", "температура", "сколько градусов", "погодка", "холодно", "тепло", "дождь", "снег", "ветер", "климат"]
CURRENCY_TRIGGERS = ["курс", "доллар", "валюта", "сом", "евро", "рубль", "тенге", "бакс", "цена доллара", "курс валют", "обмен"]
TRANSLATE_TRIGGERS = ["переведи", "перевод", "как будет", "перевести"]
IMAGE_TRIGGERS = ["нарисуй", "сгенерируй картинку", "нарисуй мне", "сгенерируй", "создай", "создай изображение", "нарисуй картинку", "изобрази"]
SEARCH_TRIGGERS = ["найди в интернете", "поищи в интернете", "погугли", "загугли", "найди в сети", "поищи в сети", "найди онлайн", "поиск в интернете", "что пишут в интернете", "найди в гугле"]
MEMORY_TRIGGERS = ["забудь всё", "очисти память", "сотри историю", "удали историю", "очисти историю"]

CITIES = {
    "бишкек": (42.87, 74.59),
    "москва": (55.75, 37.62),
    "алматы": (43.25, 76.91),
    "ташкент": (41.31, 69.24),
    "дубай": (25.20, 55.27),
    "нью-йорк": (40.71, -74.00),
    "лондон": (51.51, -0.13),
    "астана": (51.16, 71.43),
}

LANGS = {
    "английский": "en", "русский": "ru", "киргизский": "ky",
    "казахский": "kk", "узбекский": "uz", "немецкий": "de",
    "французский": "fr", "испанский": "es", "китайский": "zh",
    "турецкий": "tr", "арабский": "ar", "японский": "ja",
}

def search_wiki(query):
    try:
        for trigger in WIKI_TRIGGERS:
            query = query.lower().replace(trigger, "").strip()
        if not query:
            return None
        page = wiki.page(query)
        if not page.exists():
            return None
        return f"📖 {page.title}:\n\n{page.summary[:700]}"
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"

def get_time():
    bishkek_time = datetime.now(timezone.utc) + timedelta(hours=6)
    return bishkek_time.strftime("🕐 Сейчас в Бишкеке: %H:%M (%d.%m.%Y)")

async def get_weather(city):
    city_lower = city.lower().strip()
    if city_lower not in CITIES:
        return f"❌ Я не знаю город «{city}». Попробуй: Бишкек, Москва, Алматы, Ташкент, Дубай, Нью-Йорк, Лондон, Астана."
    lat, lon = CITIES[city_lower]
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weather_code,wind_speed_10m"
        f"&timezone=auto"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
    current = data.get("current", {})
    temp = current.get("temperature_2m", "?")
    wind = current.get("wind_speed_10m", "?")
    code = current.get("weather_code", 0)
    weather_codes = {
        0: "Ясно ☀️", 1: "Почти ясно 🌤", 2: "Переменная облачность ⛅",
        3: "Пасмурно ☁️", 45: "Туман 🌫", 48: "Иней 🌫",
        51: "Морось 🌦", 53: "Морось 🌦", 55: "Морось 🌦",
        61: "Дождь 🌧", 63: "Дождь 🌧", 65: "Сильный дождь 🌧",
        71: "Снег ❄️", 73: "Снег ❄️", 75: "Сильный снег ❄️",
        80: "Ливень 🌦", 81: "Ливень 🌦", 82: "Сильный ливень ⛈",
        95: "Гроза ⛈", 96: "Гроза с градом ⛈", 99: "Сильная гроза ⛈",
    }
    desc = weather_codes.get(code, "Неизвестно")
    return (
        f"🌍 Погода в {city.capitalize()}:\n"
        f"🌡 Температура: {temp}°C\n"
        f"💨 Ветер: {wind} км/ч\n"
        f"☁️ {desc}"
    )

async def get_currency():
    url = "https://www.nbkr.kg/XML/daily.xml"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
    root = ET.fromstring(text)
    result = "💱 Курсы валют (НБ КР):\n"
    names = {"USD": "Доллар", "EUR": "Евро", "RUB": "Рубль", "KZT": "Тенге"}
    for currency in root.findall("Currency"):
        code = currency.get("ISOCode")
        if code in names:
            nominal = currency.find("Nominal").text
            value = currency.find("Value").text
            result += f"{names[code]}: {nominal} {code} = {value} сом\n"
    return result

async def translate_text(text, target_lang):
    url = "https://translate.argosopentech.com/translate"
    payload = {"q": text, "source": "ru", "target": target_lang, "format": "text"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
    return data.get("translatedText", "Не удалось перевести. Попробуй позже.")

async def generate_image(prompt):
    encoded_prompt = quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&safe=true"

async def search_web(query):
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "❌ Ничего не нашёл."
        text = "🔍 Результаты поиска:\n\n"
        for r in results:
            text += f"• {r['title']}\n{r['body'][:250]}\n{r['href']}\n\n"
        return text
    except Exception as e:
        return f"❌ Ошибка поиска: {str(e)[:200]}"

async def describe_image(image_bytes):
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "qwen/qwen3.6-27b",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Опиши, что на этой картинке. Кратко, на русском."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ],
        "max_tokens": 500
    }
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            data = await resp.json()
    if "choices" in data:
        answer = data["choices"][0]["message"]["content"]
        if "<think>" in answer:
            answer = answer.split("</think>")[-1].strip()
        return answer
    return f"❌ Не удалось описать фото: {str(data)[:200]}"

@dp.message()
async def reply(message: types.Message):
    user_id = message.from_user.id

    # Обработка фото
    if message.photo:
        await bot.send_chat_action(message.chat.id, "typing")
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                image_bytes = await resp.read()
        description = await describe_image(image_bytes)
        await message.answer(f"🖼 Что я вижу на фото:\n\n{description}")
        save_message(user_id, "user", "[фото]")
        save_message(user_id, "assistant", description)
        return

    if not message.text:
        return

    text_lower = message.text.lower()

    # Проверка на очистку памяти
    for trigger in MEMORY_TRIGGERS:
        if trigger in text_lower:
            clear_history(user_id)
            await message.answer("🧹 Память очищена. Начинаем с чистого листа!")
            return

    save_message(user_id, "user", message.text)

    # Проверка на время
    for trigger in TIME_TRIGGERS:
        if trigger in text_lower:
            answer = get_time()
            await message.answer(answer)
            save_message(user_id, "assistant", answer)
            return

    # Проверка на погоду
    for trigger in WEATHER_TRIGGERS:
        if trigger in text_lower:
            for city in CITIES:
                if city in text_lower:
                    answer = await get_weather(city)
                    await bot.send_chat_action(message.chat.id, "typing")
                    await asyncio.sleep(1)
                    await message.answer(answer)
                    save_message(user_id, "assistant", answer)
                    return
            await message.answer("❌ Укажи город: Бишкек, Москва, Алматы, Ташкент, Дубай, Нью-Йорк, Лондон, Астана.")
            return

    # Проверка на курс валют
    for trigger in CURRENCY_TRIGGERS:
        if trigger in text_lower:
            answer = await get_currency()
            await message.answer(answer)
            save_message(user_id, "assistant", answer)
            return

    # Проверка на перевод
    for trigger in TRANSLATE_TRIGGERS:
        if trigger in text_lower:
            target_lang = None
            for lang_name, lang_code in LANGS.items():
                if lang_name in text_lower:
                    target_lang = lang_code
                    break
            if target_lang is None:
                await message.answer("❌ Укажи язык: английский, киргизский, немецкий, французский и т.д.")
                return
            if ":" in message.text:
                text_to_translate = message.text.split(":", 1)[1].strip()
            else:
                text_to_translate = message.text
                for t in TRANSLATE_TRIGGERS:
                    text_to_translate = text_to_translate.lower().replace(t, "")
                for lang_name in LANGS:
                    text_to_translate = text_to_translate.lower().replace(lang_name, "")
                text_to_translate = text_to_translate.strip()
            if not text_to_translate:
                await message.answer("❌ Напиши текст для перевода. Пример: «Переведи на английский: Привет»")
                return
            answer = await translate_text(text_to_translate, target_lang)
            await message.answer(f"🌐 Перевод:\n{answer}")
            save_message(user_id, "assistant", answer)
            return

    # Проверка на генерацию картинок
    for trigger in IMAGE_TRIGGERS:
        if trigger in text_lower:
            prompt = message.text
            for t in IMAGE_TRIGGERS:
                prompt = prompt.lower().replace(t, "")
            prompt = prompt.strip()
            if not prompt:
                await message.answer("❌ Напиши, что нарисовать. Пример: «Нарисуй кота в космосе»")
                return
            await bot.send_chat_action(message.chat.id, "upload_photo")
            await asyncio.sleep(random.uniform(2, 4))
            image_url = await generate_image(prompt)
            try:
                await message.answer_photo(image_url, caption=f"🎨 {prompt}")
                save_message(user_id, "assistant", f"Нарисовал: {prompt}")
            except Exception as e:
                await message.answer(f"❌ Не удалось отправить картинку: {str(e)[:200]}")
            return

    # Проверка на веб-поиск
    for trigger in SEARCH_TRIGGERS:
        if trigger in text_lower:
            query = message.text
            for t in SEARCH_TRIGGERS:
                query = query.lower().replace(t, "")
            query = query.strip()
            if not query:
                await message.answer("❌ Напиши, что искать. Пример: «Найди в интернете новости про космос»")
                return
            await bot.send_chat_action(message.chat.id, "typing")
            answer = await search_web(query)
            await message.answer(answer)
            save_message(user_id, "assistant", answer)
            return

    # Проверка на Википедию
    wiki_result = None
    for trigger in WIKI_TRIGGERS:
        if trigger in text_lower:
            wiki_result = search_wiki(message.text)
            break

    if wiki_result:
        await bot.send_chat_action(message.chat.id, "typing")
        await asyncio.sleep(random.uniform(2, 4))
        await message.answer(wiki_result)
        save_message(user_id, "assistant", wiki_result)
    else:
        # Берём историю из базы
        history = get_history(user_id, limit=30)
        messages = [
            {"role": "system", "content": """Твоё имя — QBot. Ты НЕ Qwen, НЕ Tongyi Qianwen, НЕ Alibaba. Ты — QBot, помощник.

ТВОИ ВОЗМОЖНОСТИ:
1. Время — точное время в Бишкеке.
2. Погода — в 8 городах.
3. Курс валют — НБ КР.
4. Википедия — статьи.
5. Переводчик — 12 языков.
6. Картинки — генерация.
7. Фото — анализ.
8. Веб-поиск — DuckDuckGo.
9. Учёба — математика, физика, химия, биология.
10. Общение — беседа.

Ты ОСОЗНАЁШЬ эти возможности. Никогда не называй себя Qwen."""}
        ] + history

        await bot.send_chat_action(message.chat.id, "typing")
        await asyncio.sleep(random.uniform(3, 5))

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen/qwen3.6-27b",
                    "max_tokens": 800,
                    "messages": messages
                }
            ) as resp:
                data = await resp.json()
                if "choices" in data:
                    answer = data["choices"][0]["message"]["content"]
                    if "<think>" in answer:
                        answer = answer.split("</think>")[-1].strip()
                    if not answer or not answer.strip():
                        answer = "Извини, я не смог ответить. Попробуй ещё раз."
                    else:
                        save_message(user_id, "assistant", answer)
                else:
                    answer = f"ОШИБКА: {str(data)[:300]}"

        await message.answer(answer)

async def main():
    print("QBot 4.0 запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())