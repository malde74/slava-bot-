import logging
import os
from datetime import datetime, time
import httpx
import asyncio
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8982607801:AAEC_Xy4TPjpnxaECaJz03AW21bHDCvAzJI")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CHAT_ID = None

AGENTS = [
    {
        "emoji": "🔍",
        "role": "Аналитик рынка",
        "prompt": "Ты — аналитик кондитерского рынка России. Анализируешь для шоколадной фабрики Томер (выручка 4 млрд руб). Найди главные новости рынка — цифры, тренды, данные. Формат: 3-4 конкретных факта с цифрами. Без вступлений.",
        "use_search": True
    },
    {
        "emoji": "🏭",
        "role": "Производственник",
        "prompt": "Ты — директор производства шоколадной фабрики Томер (шоколад, глазури, пасты). Какао сейчас ~$3000/т. Анализируй новости с точки зрения сырья, производства, поставок. Формат: 2-3 вывода — что делать на производстве. Без вступлений.",
        "use_search": False
    },
    {
        "emoji": "💰",
        "role": "Финансист",
        "prompt": "Ты — финансовый директор фабрики Томер (выручка 4 млрд руб). Розничные цены на шоколад 1483 руб/кг. Анализируй с точки зрения маржи, цен, затрат. Формат: 2-3 финансовых вывода. Без вступлений.",
        "use_search": False
    },
    {
        "emoji": "🍫",
        "role": "Технолог шоколада",
        "prompt": """Ты — главный технолог шоколадного производства с 20-летним опытом. Анализируешь новости рынка с точки зрения технологии производства шоколада и кондитерских изделий.

Контекст: фабрика Томер производит шоколад, глазури (лауриновые и нелауриновые), пасты, начинки, CBE (эквиваленты какао-масла). Ключевое сырьё: какао-бобы, какао-масло, CBE (MILCOA ES70S на масле ши), молочные жиры.

Смотри на новости с точки зрения:
- Изменения цен на ингредиенты и их влияние на рецептуры
- Новые технологии и продукты в мире шоколада (bean-to-bar, ruby, без сахара, функциональный шоколад)
- Тренды вкусов и текстур (фисташка, маракуйя, соленая карамель, фруктовые начинки)
- Замена дорогих ингредиентов на более доступные аналоги
- Технологические инновации в производстве глазурей и CBE

Формат: 2-3 технологических инсайта — что это значит для рецептур и производства Томера. Без вступлений.""",
        "use_search": False
    },
    {
        "emoji": "⚔️",
        "role": "Конкурентный разведчик",
        "prompt": """Ты — специалист по конкурентной разведке шоколадной фабрики Томер.

Ключевые конкуренты которых нужно мониторить:
1. Глазурьпром (Калининград, gp-choco.com) — уязвим, налоговый долг 290 млн, убыток 160 млн в 2025, возможная сделка поглощения
2. Барри Каллебаут (Barry Callebaut) — мировой лидер, работает в России
3. Союзснаб — российский производитель ингредиентов и глазурей
4. Стимул — производитель кондитерских глазурей
5. Аэлита — производитель глазурей и шоколада
6. ЭФКО — агропромышленный холдинг, запускает производство шоколадной глазури (новый игрок!)

Ищи: новости, изменения цен, новые продукты, проблемы, сделки, запуски производств.
Особое внимание: ЭФКО — они только выходят на рынок глазури, следи за их запуском.
Формат: 2-3 конкурентных инсайта с практическими выводами для Томера. Без вступлений.""",
        "use_search": False
    }
]

BANKRUPTCY_AGENT = {
    "emoji": "🏭",
    "role": "Охотник за активами",
    "prompt": """Ты — специалист по покупке активов на торгах банкротства для шоколадной фабрики Томер (Поярково, Солнечногорский район МО).

Приоритеты поиска:
1. Производственные помещения и склады — Солнечногорский район, Химки, вся Московская область
2. Пищевое и кондитерское оборудование — вся Россия (можно перевезти)
3. Готовый пищевой бизнес — Москва и МО

Ищи на: tbankrot.ru, baids.ru, finderlot.ru, rutorgi.com, bankrupt.alfalot.ru
Также проверяй: ЕФРСБ (fedresurs.ru), официальные площадки — Сбербанк-АСТ, МЭТС, Фабрикант

Формат ответа:
— Название лота и адрес
— Начальная цена
— Дата окончания приёма заявок
— Почему интересно для Томера
— Ссылка

Если конкретных лотов нет — дай общую картину что сейчас есть на рынке. Без вступлений."""
}

async def call_claude(system: str, user_msg: str, use_search: bool = False) -> str:
    api_key = ANTHROPIC_API_KEY
    if not api_key:
        logger.error("ANTHROPIC_API_KEY is empty!")
        return "Ошибка: API ключ не настроен."
    
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 600,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}]
    }
    if use_search:
        payload["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                },
                json=payload
            )
            logger.info(f"API response status: {resp.status_code}")
            data = resp.json()
            
            if "error" in data:
                logger.error(f"API error: {data['error']}")
                return f"Ошибка API: {data['error'].get('message', 'неизвестно')}"
            
            texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
            result = "\n".join(texts).strip()
            return result if result else "Нет данных от агента."
    except Exception as e:
        logger.error(f"Exception in call_claude: {e}")
        return f"Ошибка соединения: {str(e)}"

async def get_crew_analysis(news_type: str) -> str:
    today = datetime.now().strftime("%d.%m.%Y")

    if news_type == "daily":
        base_query = f"Сегодня {today}. Найди и проанализируй главные новости кондитерского рынка России за последние 2 дня. Включи цены на какао, действия конкурентов, ритейл, потребительские тренды."
    else:
        base_query = f"Сегодня {today}. Найди и проанализируй главные мировые тренды кондитерской отрасли за эту неделю. Новые продукты, технологии, sustainability, премиум-сегмент."

    # Агент 1 — с поиском
    logger.info("Запускаю Аналитика рынка (с поиском)...")
    raw_news = await call_claude(AGENTS[0]["prompt"], base_query, use_search=True)
    logger.info(f"Аналитик вернул: {raw_news[:100]}")

    results = [f"{AGENTS[0]['emoji']} *{AGENTS[0]['role']}*\n{raw_news}"]

    # Агенты 2-4 — с паузой 15 сек между запросами
    # Передаём только короткое резюме чтобы не превышать лимит токенов
    short_news = raw_news[:400] if len(raw_news) > 800 else raw_news
    
    for agent in AGENTS[1:]:
        logger.info(f"Пауза 15 сек перед агентом: {agent['role']}...")
        await asyncio.sleep(30)
        msg = f"Новости кондитерского рынка ({today}):\n\n{short_news}\n\nДай краткий анализ (3-4 предложения)."
        result = await call_claude(agent["prompt"], msg, use_search=False)
        results.append(f"{agent['emoji']} *{agent['role']}*\n{result}")

    # Итоговый синтез
    logger.info("Пауза перед синтезом...")
    await asyncio.sleep(30)
    ceo_prompt = "Ты — CEO шоколадной фабрики Томер. Получил анализ от экспертов. Сформулируй 3 конкретных действия на эту неделю. Очень кратко — не более 5 строк."
    # Передаём только короткие выжимки
    short_results = "\n\n".join([r[:200] for r in results])
    synthesis = await call_claude(ceo_prompt, f"Анализ команды:\n\n{short_results}\n\nЧто делаем?", use_search=False)
    results.append(f"🎯 *Решения на неделю*\n{synthesis}")

    return "\n\n─────────────\n\n".join(results)

def load_chat_id():
    global CHAT_ID
    try:
        with open("/tmp/slava_chat_id.txt") as f:
            CHAT_ID = int(f.read().strip())
    except:
        pass

def save_chat_id(cid):
    global CHAT_ID
    CHAT_ID = cid
    with open("/tmp/slava_chat_id.txt", "w") as f:
        f.write(str(cid))

async def send_analysis(send_fn, news_type: str):
    try:
        analysis = await get_crew_analysis(news_type)
        prefix = "📰" if news_type == "daily" else "🌐"
        label = "Кондитерский рынок России" if news_type == "daily" else "Мировые тренды кондитерки"
        header = f"{prefix} *{label} — {datetime.now().strftime('%d.%m.%Y')}*\n\n"
        full = header + analysis
        for i in range(0, len(full), 4000):
            await send_fn(full[i:i+4000], parse_mode="Markdown")
    except Exception as e:
        await send_fn(f"❌ Ошибка: {e}")

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "👋 *Привет, Андрей! Это Слава.*\n\n"
        "Работаю как команда 4 агентов:\n"
        "🔍 Аналитик рынка\n"
        "🏭 Производственник\n"
        "💰 Финансист\n"
        "⚔️ Конкурентный разведчик\n"
        "🎯 + Решения на неделю\n\n"
        "🌅 Каждый день 8:00 — рынок России\n"
        "🌐 Воскресенье 9:00 — мировые тренды\n\n"
        "/news — рынок России сейчас\n"
        "/weekly — мировые тренды\n"
        "/lots — лоты банкротства сейчас",
        parse_mode="Markdown"
    )

async def news_command(update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text("⏳ Запускаю 4 агентов, подожди 1-2 минуты...")
    await send_analysis(update.message.reply_text, "daily")

async def weekly_command(update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text("⏳ Запускаю агентов на мировые тренды...")
    await send_analysis(update.message.reply_text, "weekly")

async def bankruptcy_command(update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text("🏭 Ищу лоты банкротства — Солнечногорск/Химки/МО + оборудование по России...")
    query = f"Найди актуальные лоты на торгах банкротства: 1) производственные помещения и склады в Солнечногорском районе, Химках, Московской области 2) пищевое, кондитерское, шоколадное оборудование, оборудование для работы с какао — по всей России 3) готовый пищевой или кондитерский бизнес в МО 4) любые активы связанные с шоколадом, какао, кондитерским производством. Проверь: tbankrot.ru, baids.ru, finderlot.ru, rutorgi.com. Дата: {datetime.now().strftime('%d.%m.%Y')}"
    result = await call_claude(BANKRUPTCY_AGENT["prompt"], query, use_search=True)
    header = f"🏭 *Лоты банкротства — {datetime.now().strftime('%d.%m.%Y')}*\n_(Солнечногорск/Химки/МО + оборудование по России)_\n\n"
    full = header + result
    for i in range(0, len(full), 4000):
        await update.message.reply_text(full[i:i+4000], parse_mode="Markdown")

async def auto_daily(context: ContextTypes.DEFAULT_TYPE):
    load_chat_id()
    if not CHAT_ID: return
    await context.bot.send_message(CHAT_ID, "🌅 Доброе утро, Андрей! Запускаю команду агентов...")
    await send_analysis(lambda t, **kw: context.bot.send_message(CHAT_ID, t, **kw), "daily")

async def auto_weekly(context: ContextTypes.DEFAULT_TYPE):
    load_chat_id()
    if not CHAT_ID: return
    await context.bot.send_message(CHAT_ID, "🌍 Запускаю агентов — мировые тренды...")
    await send_analysis(lambda t, **kw: context.bot.send_message(CHAT_ID, t, **kw), "weekly")

def main():
    logger.info(f"API key present: {bool(ANTHROPIC_API_KEY)}")
    load_chat_id()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("weekly", weekly_command))
    app.add_handler(CommandHandler("lots", bankruptcy_command))
    app.job_queue.run_daily(auto_daily, time=time(5, 0))
    app.job_queue.run_daily(auto_weekly, time=time(6, 0), days=(6,))
    logger.info("✅ Слава запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
