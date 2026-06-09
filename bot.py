import os
import logging
import anthropic
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# Хранилище chat_id пользователей (в памяти; при рестарте очищается)
subscribers: set[int] = set()

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def ask_claude(prompt: str) -> str:
    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def get_ru_news() -> str:
    prompt = (
        "Ты аналитик кондитерского рынка России. "
        "Составь краткую сводку актуальных новостей и трендов российского кондитерского рынка "
        "за последние дни (новые продукты, изменения цен, крупные игроки, потребительские тренды). "
        "Формат: 5–7 пунктов, каждый с заголовком жирным и коротким описанием. "
        "Пиши на русском языке, деловым стилем."
    )
    return ask_claude(prompt)


def get_world_digest() -> str:
    prompt = (
        "Ты аналитик мирового кондитерского рынка. "
        "Составь воскресный дайджест мировых трендов и инноваций в кондитерской отрасли: "
        "новые технологии, ингредиенты, упаковка, международные выставки, крупные сделки. "
        "Формат: 5–7 пунктов, каждый с заголовком жирным и коротким описанием. "
        "Пиши на русском языке, деловым стилем."
    )
    return ask_claude(prompt)


# ── Команды ────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    await update.message.reply_text(
        "👋 Привет! Я *Слава* — бот мониторинга кондитерского рынка.\n\n"
        "🌅 Каждый день в *8:00 (Москва)* — новости российского рынка\n"
        "🌐 Каждое *воскресенье в 9:00* — мировые тренды\n\n"
        "Ты подписан на автоматическую рассылку ✅\n\n"
        "Доступные команды:\n"
        "/news — новости прямо сейчас\n"
        "/weekly — мировой дайджест прямо сейчас\n"
        "/help — помощь",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*Команды Славы:*\n\n"
        "/start — активация и подписка\n"
        "/news — сводка новостей кондитерского рынка России\n"
        "/weekly — мировые тренды и инновации\n"
        "/help — это сообщение",
        parse_mode="Markdown",
    )


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Собираю новости, подожди 30–60 секунд…")
    try:
        text = get_ru_news()
        await update.message.reply_text(
            f"🌅 *Кондитерский рынок России — {datetime.now(MOSCOW_TZ).strftime('%d.%m.%Y')}*\n\n{text}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Ошибка /news: %s", e)
        await update.message.reply_text("❌ Ошибка при получении новостей. Проверь ANTHROPIC_API_KEY.")


async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Готовлю мировой дайджест, подожди…")
    try:
        text = get_world_digest()
        await update.message.reply_text(
            f"🌐 *Мировые тренды кондитерской отрасли — {datetime.now(MOSCOW_TZ).strftime('%d.%m.%Y')}*\n\n{text}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Ошибка /weekly: %s", e)
        await update.message.reply_text("❌ Ошибка. Проверь ANTHROPIC_API_KEY.")


# ── Авторассылка ────────────────────────────────────────────────────────────

async def daily_news_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневно в 8:00 МСК — российский рынок."""
    if not subscribers:
        return
    try:
        text = get_ru_news()
        msg = (
            f"🌅 *Кондитерский рынок России — {datetime.now(MOSCOW_TZ).strftime('%d.%m.%Y')}*\n\n{text}"
        )
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.warning("Не удалось отправить %s: %s", chat_id, e)
    except Exception as e:
        logger.error("daily_news_job error: %s", e)


async def weekly_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Каждое воскресенье в 9:00 МСК — мировые тренды."""
    if not subscribers:
        return
    try:
        text = get_world_digest()
        msg = (
            f"🌐 *Мировые тренды кондитерской отрасли — {datetime.now(MOSCOW_TZ).strftime('%d.%m.%Y')}*\n\n{text}"
        )
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.warning("Не удалось отправить %s: %s", chat_id, e)
    except Exception as e:
        logger.error("weekly_digest_job error: %s", e)


# ── Запуск ──────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("weekly", cmd_weekly))

    job_queue = app.job_queue

    # Ежедневно в 8:00 МСК
    job_queue.run_daily(
        daily_news_job,
        time=datetime.now(MOSCOW_TZ).replace(hour=8, minute=0, second=0, microsecond=0).timetz(),
        days=(0, 1, 2, 3, 4, 5, 6),
    )

    # Каждое воскресенье в 9:00 МСК (weekday 6 = воскресенье)
    job_queue.run_daily(
        weekly_digest_job,
        time=datetime.now(MOSCOW_TZ).replace(hour=9, minute=0, second=0, microsecond=0).timetz(),
        days=(6,),
    )

    logger.info("Слава запущен.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
