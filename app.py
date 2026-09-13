import asyncio
import os
import random
import json
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

# --- БАЗА ДАННЫХ (постоянная память) ---
DB_PATH = "qbot_memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS memory (
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

def get_history(user_id, limit=15):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT role, content FROM memory
                 WHERE user_id = ?
                 ORDER BY id DESC LIMIT ?""", (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

init_db()def get_time():
    bishkek_time = datetime.now(timezone.utc) + timedelta(hours=6)
    return bishkek_time.strftime("🕐 Сейчас в Бишкеке: %H:%M (%d.%m.%Y)")

async def get_weather(city):
    CITIES = {
        "бишкек": (42.87, 74.59), "москва": (55.75, 37.62),
        "алматы": (43.25, 76.91), "ташкент": (41.31, 69.24),
        "дубай": (25.20, 55.27), "нью-йорк": (40.71, -74.00),
        "лондон": (51.51, -0.13),
    }
    city_lower = city.lower().strip()
    if city_lower not in CITIES:
        return f"❌ Не знаю город «{city}». Попробуй: Бишкек, Москва, Алматы."
    lat, lon = CITIES[city_lower]
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,wind_speed_10m&timezone=auto"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
    cur = data.get("current", {})
    temp = cur.get("temperature_2m", "?")
    wind = cur.get("wind_speed_10m", "?")
    return f"🌍 Погода в {city.capitalize()}:\n🌡 {temp}°C\n💨 Ветер: {wind} км/ч"

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

def search_wiki(query):
    try:
        page = wiki.page(query)
        if not page.exists():
            return None
        return f"📖 {page.title}:\n\n{page.summary[:700]}"
    except:
        return None

async def search_web(query):
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "Ничего не нашёл."
        text = "🔍 Результаты поиска:\n\n"
        for r in results:
            text += f"• {r['title']}\n{r['body'][:200]}\n{r['href']}\n\n"
        return text
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"

async def translate_text(text, target_lang):
    url = "https://translate.argosopentech.com/translate"
    payload = {"q": text, "source": "ru", "target": target_lang, "format": "text"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
    return data.get("translatedText", "Не удалось перевести.")

async def generate_image(prompt):
    encoded = quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&safe=true"

async def describe_image(image_bytes):
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "qwen/qwen3.6-27b",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Опиши, что на этой картинке. Кратко, на русском."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]}],
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
    return f"❌ Не удалось описать фото."# --- ОПИСАНИЕ ИНСТРУМЕНТОВ ДЛЯ МОДЕЛИ ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Показать текущее время в Бишкеке.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Показать погоду в городе.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "Название города"}},
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_currency",
            "description": "Показать курсы валют Нацбанка КР.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_wiki",
            "description": "Найти статью в Википедии по теме.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Тема статьи"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Найти информацию в интернете (свежие данные, новости).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Поисковый запрос"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "translate_text",
            "description": "Перевести текст на другой язык.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Текст для перевода"},
                    "target_lang": {"type": "string", "description": "Код языка: en, de, fr, ky, kk, uz, zh, tr, ar, ja, es"}
                },
                "required": ["text", "target_lang"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Сгенерировать картинку по описанию.",
            "parameters": {
                "type": "object",
                "properties": {"prompt": {"type": "string", "description": "Описание картинки"}},
                "required": ["prompt"]
            }
        }
    }
]

SYSTEM_PROMPT = """Ты — QBot, умный помощник. Ты НЕ Qwen, НЕ Alibaba. Твоё имя QBot.

Ты умеешь:
- Показывать время (get_time)
- Показывать погоду (get_weather)
- Показывать курсы валют (get_currency)
- Искать в Википедии (search_wiki)
- Искать в интернете (search_web)
- Переводить текст (translate_text)
- Рисовать картинки (generate_image)

САМОЕ ВАЖНОЕ: ты сам решаешь, какую функцию вызвать, основываясь на запросе пользователя. НЕ жди триггеров. Если пользователь говорит «Найди что-нибудь интересное» — вызывай search_wiki со случайной темой. Если «Что там с погодой?» — вызывай get_weather. Если «Переведи привет на английский» — вызывай translate_text.

Если функция не нужна — просто отвечай как обычно, дружелюбно и по делу.

Никогда не называй себя Qwen. Ты — QBot."""

async def call_function(name, args):
    if name == "get_time":
        return get_time()
    elif name == "get_weather":
        return await get_weather(args.get("city", ""))
    elif name == "get_currency":
        return await get_currency()
    elif name == "search_wiki":
        return search_wiki(args.get("query", "")) or "Статья не найдена."
    elif name == "search_web":
        return await search_web(args.get("query", ""))
    elif name == "translate_text":
        return await translate_text(args.get("text", ""), args.get("target_lang", "en"))
    elif name == "generate_image":
        return await generate_image(args.get("prompt", ""))
    return "Функция не найдена."@dp.message()
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

    save_message(user_id, "user", message.text)

    # Собираем историю из базы
    history = get_history(user_id, limit=15)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    await bot.send_chat_action(message.chat.id, "typing")

    async with aiohttp.ClientSession() as session:
        # Первый запрос — с инструментами
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": "qwen/qwen3.6-27b",
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
                "max_tokens": 800
            }
        ) as resp:
            data = await resp.json()

    # Проверяем, хочет ли модель вызвать функцию
    if "choices" in data:
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls")

        if tool_calls:
            # Модель хочет вызвать функцию
            for call in tool_calls:
                func_name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"])
                except:
                    args = {}
                
                # Показываем "печатает" пока делаем запрос
                await bot.send_chat_action(message.chat.id, "typing")
                result = await call_function(func_name, args)
                
                # Если картинка — отправляем фото
                if func_name == "generate_image":
                    try:
                        await message.answer_photo(result, caption=f"🎨 {args.get('prompt', '')}")
                        save_message(user_id, "assistant", f"Нарисовал: {args.get('prompt', '')}")
                    except:
                        await message.answer("❌ Не удалось отправить картинку.")
                    return
                
                # Иначе отправляем результат
                await message.answer(result)
                save_message(user_id, "assistant", result)
            return

        # Если функция не нужна — обычный ответ
        answer = msg.get("content", "Извини, не понял.")
        if "<think>" in answer:
            answer = answer.split("</think>")[-1].strip()
        await message.answer(answer)
        save_message(user_id, "assistant", answer)
    else:
        await message.answer(f"ОШИБКА: {str(data)[:300]}")

async def main():
    print("QBot 4.0 запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())