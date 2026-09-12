import asyncio
import os
import random
from aiogram import Bot, Dispatcher, types
import aiohttp
import wikipediaapi
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

wiki = wikipediaapi.Wikipedia(
    user_agent='QBot/1.0 (https://t.me/AlpfyHelper_bot)',
    language='ru'
)

history = {}

TIME_TRIGGERS = ["который час", "сколько времени", "текущее время", "время сейчас"]

WIKI_TRIGGERS = [
    "кто такой", "кто такая", "кто такое",
    "что такое", "что за",
    "расскажи про", "расскажи о",
    "информация о", "информация про",
    "найди про", "найди о"
]

WEATHER_TRIGGERS = ["погода", "погоду", "температура", "сколько градусов"]

CURRENCY_TRIGGERS = ["курс", "доллар", "валюта", "сом", "евро", "рубль"]

CITIES = {
    "бишкек": (42.87, 74.59),
    "москва": (55.75, 37.62),
    "алматы": (43.25, 76.91),
    "ташкент": (41.31, 69.24),
    "дубай": (25.20, 55.27),
    "нью-йорк": (40.71, -74.00),
    "лондон": (51.51, -0.13),
}

def search_wiki(query):
    try:
        for trigger in WIKI_TRIGGERS:
            query = query.lower().replace(trigger, "").strip()
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
        return f"❌ Я не знаю город «{city}». Попробуй: Бишкек, Москва, Алматы, Ташкент, Дубай, Нью-Йорк, Лондон."
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

@dp.message()
async def reply(message: types.Message):
    user_id = message.from_user.id

    if not message.text:
        return

    text_lower = message.text.lower()

    if user_id not in history:
        history[user_id] = [
            {"role": "system", "content": "Твоё имя — QBot (произносится «Кьюбот»). Ты НЕ Qwen, НЕ Tongyi Qianwen, НЕ Alibaba. Ты — QBot, помощник. Если тебя спрашивают, кто ты — отвечай: 'Я QBot'. Никогда не называй себя Qwen или другими именами."}
        ]

    # Проверка на время
    for trigger in TIME_TRIGGERS:
        if trigger in text_lower:
            answer = get_time()
            await message.answer(answer)
            history[user_id].append({"role": "user", "content": message.text})
            history[user_id].append({"role": "assistant", "content": answer})
            history[user_id] = history[user_id][-15:]
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
                    history[user_id].append({"role": "user", "content": message.text})
                    history[user_id].append({"role": "assistant", "content": answer})
                    history[user_id] = history[user_id][-15:]
                    return
            await message.answer("❌ Укажи город: Бишкек, Москва, Алматы, Ташкент, Дубай, Нью-Йорк, Лондон.")
            return

    # Проверка на курс валют
    for trigger in CURRENCY_TRIGGERS:
        if trigger in text_lower:
            answer = await get_currency()
            await message.answer(answer)
            history[user_id].append({"role": "user", "content": message.text})
            history[user_id].append({"role": "assistant", "content": answer})
            history[user_id] = history[user_id][-15:]
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
        history[user_id].append({"role": "user", "content": message.text})
        history[user_id].append({"role": "assistant", "content": wiki_result})
        history[user_id] = history[user_id][-15:]
    else:
        history[user_id].append({"role": "user", "content": message.text})
        history[user_id] = history[user_id][-15:]

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
                    "model": "qwen/qwen3.8-27b",
                    "max_tokens": 800,
                    "messages": history[user_id]
                }
            ) as resp:
                data = await resp.json()
                if "choices" in data:
                    answer = data["choices"][0]["message"]["content"]
                    if not answer or not answer.strip():
                        answer = "Извини, я не смог ответить. Попробуй ещё раз."
                    else:
                        history[user_id].append({"role": "assistant", "content": answer})
                else:
                    answer = f"ОШИБКА: {str(data)[:300]}"

        await message.answer(answer)

async def main():
    print("QBot запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())