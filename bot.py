import logging
import os
from datetime import datetime, time
import httpx
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8982607801:AAEC_Xy4TPjpnxaECaJz03AW21bHDCvAzJI")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CHAT_ID = None

# ===== 4 АГЕНТА =====
AGENTS = [
    {
        "emoji": "🔍",
        "role": "Аналитик рынка",
        "prompt": """Ты — аналитик кондитерского рынка. Твоя задача: найти и проанализировать самые важные новости рынка с точки зрения цифр, трендов и данных.
Контекст: анализируешь для шоколадной фабрики Томер (Россия, выручка 4 млрд руб, производство шоколада и глазурей).
Формат ответа: 3-4 ключевых факта с цифрами. Без вступлений."""
    },
    {
        "emoji": "🏭",
        "role": "Производственник",
        "prompt": """Ты — директор производства шоколадной фабрики. Смотришь на новости рынка с точки зрения производства: сырьё, какао, оборудование, логистика, цепочки поставок.
Контекст: фабрика Томер производит шоколад, глазури, пасты, начинки. Какао сейчас ~$3000/т (упало с $12000).
Формат ответа: 2-3 вывода — что нужно сделать на производстве прямо сейчас. Без вступлений."""
    },
    {
        "emoji": "💰",
        "role": "Финансист",
        "prompt": """Ты — финансовый директор шоколадной фабрики. Анализируешь новости с точки зрения маржи, цен, затрат и финансовых рисков.
Контекст: фабрика Томер, выручка 4 млрд руб. Розничные цены на шоколад в РФ выросли до 1483 руб/кг. Продажи шоколада падают второй год.
Формат ответа: 2-3 финансовых вывода с рекомендациями по ценообразованию или затратам. Без вступлений."""
    },
    {
        "emoji": "⚔️",
        "role": "Конкурентный разведчик",
        "prompt": """Ты — специалист по конкурентной разведке в кондитерской отрасли. Ищешь в новостях сигналы о действиях конкурентов, новых игроках, изменениях на рынке.
Контекст: главные конкуренты Томера — Глазурьпром (сейчас в уязвимом положении, умер собственник), другие производители глазурей и шоколада в РФ.
Формат ответа: 2-3 конкурентных инсайта и что с этим делать. Без вступлений."""
    }
]

async def call_claude(system: str, user_prompt: str, use_search: bool = True) -> str:
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 600,
        "system": system,
        "messages": [{"role": "user", "content": user_prompt}]
    }
    if use_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json=payload
        )
        data = response.json()
        text_parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        return "\n".join(text_parts) or "Нет данных."

async def get_crew_analysis(news_type: str) -> str:
    today = datetime.now().strftime("%d.%m.%Y")

    # Шаг 1 — Аналитик собирает новости (с поиском)
    if news_type == "daily":
        base_query = f"Найди главные новости кондитерского рынка России за последние 2 дня ({today}). Цены на какао, конкуренты, ритейл, регуляторика."
    else:
        base_query = f"Найди главные мировые тренды и инновации кондитерской отрасли за эту неделю ({today}). Технологии, новые продукты, sustainability, премиум."

    logger.info("Агент 1: сбор новостей...")
    raw_news = await call_claude(AGENTS[0]["prompt"], base_query, use_search=True)

    # Шаги 2-4 — остальные агенты анализируют без поиска
    results = [f"{AGENTS[0]['emoji']} *{AGENTS[0]['role']}*\n{raw_news}"]

    for agent in AGENTS[1:]:
        logger.info(f"Агент: {agent['role']}...")
        analysis_query = f"Вот новости кондитерского рынка на {today}:\n\n{raw_news}\n\nДай свой анализ с позиции твоей роли."
        result = await call_claude(agent["prompt"], analysis_query, use_search=False)
        results.append(f"{agent['emoji']} *{agent['role']}*\n{result}")

    # Шаг 5 — итоговый вывод
    logger.info("Финальный синтез...")
    synthesis_prompt = """Ты — CEO шоколадной фабрики Томер. Тебе принесли анализ от 4 экспертов. 
Сделай финальный вывод: 2-3 конкретных действия на эту неделю. Очень кратко и по делу."""
    
    all_analysis = "\n\n".join(results)
    synthesis = await call_claude(
        synthesis_prompt,
        f"Анализ экспертов:\n\n{all_analysis}\n\nЧто делаем на этой неделе?",
        use_search=False
    )
    results.append(f"🎯 *Решения на неделю*\n{synthesis}")

    return "\n\n─────────────────\n\n".join(results)

async def send_daily_news(context: ContextTypes.DEFAULT_TYPE):
    load_chat_id()
    if not CHAT_ID:
        return
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=f"🌅 Доброе утро, Андрей!\n\nЗапускаю команду из 4 агентов — анализируем рынок...",
    )
    try:
        analysis = await get_crew_analysis("daily")
        header = f"📰 *Кондитерский рынок России — {datetime.now().strftime('%d.%m.%Y')}*\n\n"
        # Telegram limit 4096 chars — split if needed
        full_text = header + analysis
        for i in range(0, len(full_text), 4000):
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=full_text[i:i+4000],
                parse_mode="Markdown"
            )
    except Exception as e:
        await context.bot.send_message(chat_id=CHAT_ID, text=f"Ошибка: {e}")

async def send_weekly_digest(context: ContextTypes.DEFAULT_TYPE):
    load_chat_id()
    if not CHAT_ID:
        return
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="🌍 Запускаю команду агентов — анализируем мировые тренды...",
    )
    try:
        analysis = await get_crew_analysis("weekly")
        header = f"🌐 *Мировые тренды кондитерки — {datetime.now().strftime('%d.%m.%Y')}*\n\n"
        full_text = header + analysis
        for i in range(0, len(full_text), 4000):
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=full_text[i:i+4000],
                parse_mode="Markdown"
            )
    except Exception as e:
        await context.bot.send_message(chat_id=CHAT_ID, text=f"Ошибка: {e}")

def load_chat_id():
    global CHAT_ID
    try:
        with open("/tmp/slava_chat_id.txt", "r") as f:
            CHAT_ID = int(f.read().strip())
    except:
        pass

def save_chat_id(chat_id):
    global CHAT_ID
    CHAT_ID = chat_id
    with open("/tmp/slava_chat_id.txt", "w") as f:
        f.write(str(chat_id))

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "👋 *Привет, Андрей! Это Слава.*\n\n"
        "Теперь работаю как команда из 4 агентов:\n"
        "🔍 Аналитик рынка\n"
        "🏭 Производственник\n"
        "💰 Финансист\n"
        "⚔️ Конкурентный разведчик\n"
        "🎯 + итоговые решения на неделю\n\n"
        "📅 *Расписание:*\n"
        "🌅 Каждый день в 8:00 — рынок России\n"
        "🌐 Воскресенье в 9:00 — мировые тренды\n\n"
        "Команды:\n"
        "/news — анализ прямо сейчас\n"
        "/weekly — мировой дайджест сейчас\n\n"
        "Готов! 🚀",
        parse_mode="Markdown"
    )

async def news_command(update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text("⏳ Запускаю 4 агентов, подожди 1-2 минуты...")
    analysis = await get_crew_analysis("daily")
    header = f"📰 *Кондитерский рынок России — {datetime.now().strftime('%d.%m.%Y')}*\n\n"
    full_text = header + analysis
    for i in range(0, len(full_text), 4000):
        await update.message.reply_text(full_text[i:i+4000], parse_mode="Markdown")

async def weekly_command(update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text("⏳ Запускаю 4 агентов на мировые тренды...")
    analysis = await get_crew_analysis("weekly")
    header = f"🌐 *Мировые тренды кондитерки — {datetime.now().strftime('%d.%m.%Y')}*\n\n"
    full_text = header + analysis
    for i in range(0, len(full_text), 4000):
        await update.message.reply_text(full_text[i:i+4000], parse_mode="Markdown")

def main():
    load_chat_id()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("weekly", weekly_command))

    jq = app.job_queue
    jq.run_daily(send_daily_news, time=time(5, 0))
    jq.run_daily(send_weekly_digest, time=time(6, 0), days=(6,))

    logger.info("✅ Слава (4 агента) запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
