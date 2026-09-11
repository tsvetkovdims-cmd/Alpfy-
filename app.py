import asyncio
import os
import random
from flask import Flask
from aiogram import Bot, Dispatcher, types
import aiohttp
import wikipediaapi

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

wiki = wikipediaapi.Wikipedia(
    user_agent='AlpfyBot/1.0 (https://t.me/AlpfyHelper_bot)',
    language='ru'
)

history = {}

WIKI_TRIGGERS = [
    "кто такой", "кто такая", "кто такое",
    "что такое", "что за",
    "расскажи про", "расскажи о",
    "информация о", "информация про",
    "найди про", "найди о"
]

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

@dp.message()
async def reply(message: types.Message):
    user_id = message.from_user.id
    text_lower = message.text.lower()

    if user_id not in history:
        history[user_id] = [
            {"role": "system", "content": "Ты — Альфу, дружелюбный помощник. Отвечай на русском, коротко и по делу."}
        ]

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
        history[user_id] = history[user_id][-50:]
    else:
        history[user_id].append({"role": "user", "content": message.text})
        history[user_id] = history[user_id][-50:]

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

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def run_bot():
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    import threading
    thread = threading.Thread(target=run_bot)
    thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
