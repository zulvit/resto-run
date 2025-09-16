import os
import csv
import re
import asyncio
import logging
from datetime import datetime
from io import BytesIO, StringIO
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from telegram.request import HTTPXRequest

# ───────  ЛОГИРОВАНИЕ ───────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("restaurant_report_bot")

# ───────  НАСТРОЙКИ ───────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
secrets_path = os.getenv("TELEGRAM_TOKEN_SECRET_PATH", "/run/secrets/telegram_token")
if not BOT_TOKEN and os.path.exists(secrets_path):
    try:
        with open(secrets_path, "r") as f:
            BOT_TOKEN = f.read().strip()
    except Exception:
        logger.exception("Не удалось прочитать секретный токен")

if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не задан. Завершение.")
    raise SystemExit(1)

# ───────  РЕГУЛЯРКИ ───────
DATE_RE  = re.compile(r"\b(\d{2}\.\d{2}\.(?:\d{4}|\d{2}))\b")
TIME_RE  = re.compile(r"\b(\d{1,2}[.:,]\d{2})\b")
ORDER_RE = re.compile(r"(обед[^.]*)[.\s]", re.I)

# ───────  ПАРСИНГ НАЗВАНИЯ ───────
def parse_deal_title(title: str):
    if "ресторан" not in title.lower():
        raise ValueError("не найдено слово «Ресторан»")
    d_match = DATE_RE.search(title)
    if not d_match:
        raise ValueError("не найдена дата")
    day, mon, year = d_match.group(1).split(".")
    year = "20"+year if len(year) == 2 else year
    date = datetime.strptime(f"{day}.{mon}.{year}", "%d.%m.%Y").strftime("%d.%m.%Y")
    tail = title[d_match.end():]
    t_match = TIME_RE.search(tail)
    if not t_match:
        raise ValueError("не найдено время")
    raw_time = t_match.group(1).replace(",", ":").replace(".", ":")
    if len(raw_time) == 4:
        raw_time = "0" + raw_time
    time = raw_time
    o_match = ORDER_RE.search(tail)
    fallback_order = o_match.group(1).strip() if o_match else "Обед"
    return date, time, fallback_order

# ───────  CSV → CSV + итоги ───────
def transform_csv(raw: BytesIO):
    text = raw.getvalue().decode("utf-8")
    reader = csv.DictReader(StringIO(text), delimiter=";", quotechar='"')
    out_buf, writer = StringIO(), None
    totals_amt = totals_disc = totals_final = 0.0
    errors, ok_rows = [], 0

    for n, row in enumerate(reader, start=2):
        title = row.get("Название сделки","").strip()
        company = row.get("Компания","").strip()
        guests = row.get("Количество","").strip()
        amount = row.get("Сумма","").replace(",",".").strip()
        order = row.get("Товар","").strip()

        if not company:
            errors.append(f"🚨 Стр.{n}: нет компании — «{title}»")
            continue
        try:
            guests_i = int(float(guests))
            if guests_i <= 0: raise ValueError
        except ValueError:
            errors.append(f"🚨 Стр.{n}: неправильное количество «{guests}» — «{title}»")
            continue

        try:
            date, time, fallback_order = parse_deal_title(title)
        except ValueError as e:
            errors.append(f"🚨 Стр.{n}: «{title}» — {e}")
            continue

        order = order or fallback_order
        try:
            amt = float(amount)
        except ValueError:
            amt = 0.0
        disc = round(amt * 0.15, 2)
        final = round(amt - disc, 2)

        if writer is None:
            writer = csv.writer(out_buf)
            writer.writerow([
                "Дата","Время","Место","Заказ","Компания",
                "Количество","Сумма, Руб.","Скидка 15%","Сумма за -15%"
            ])
        writer.writerow([date, time, "Ресторан", order, company, guests_i, amt, disc, final])
        totals_amt += amt
        totals_disc += disc
        totals_final += final
        ok_rows += 1

    if writer is None:
        writer = csv.writer(out_buf)
        writer.writerow(["Нет валидных строк"])

    res = BytesIO(out_buf.getvalue().encode("utf-8"))
    res.seek(0)
    return res, errors, ok_rows, totals_amt, totals_disc, totals_final

# ───────  TG-БОТ ───────
async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} вызвал /start")
    await update.message.reply_text("Привет! 👋 Пришлите CSV — верну отчёт и итоги.")

async def handle_file(update: Update, _: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    if not doc.file_name.lower().endswith(".csv"):
        await update.message.reply_text("⚠️ Нужен файл *.CSV*")
        logger.warning(f"User {user_id} прислал не CSV: {doc.file_name}")
        return

    await update.message.reply_text("📥 Файл получен, обрабатываю…")
    logger.info(f"User {user_id} прислал файл: {doc.file_name}")

    buf = BytesIO()
    await (await doc.get_file()).download_to_memory(out=buf)

    try:
        res, errs, ok_rows, total_amt, total_disc, total_final = await asyncio.to_thread(transform_csv, buf)
        caption = (
            f"✅ Готово!\n"
            f"Строк обработано: {ok_rows}\n\n"
            f"*Итоги:*\n"
            f"• без скидки: {total_amt:,.2f} ₽\n"
            f"• скидка 15%: {total_disc:,.2f} ₽\n"
            f"• со скидкой: {total_final:,.2f} ₽"
        )
        await update.message.reply_document(InputFile(res, "output.csv"), caption=caption, parse_mode="Markdown")
        logger.info(f"User {user_id}: файл обработан, строки {ok_rows}, ошибки {len(errs)}")
        if errs:
            txt = "‼️ Ошибки:\n\n" + "\n".join(errs)
            for i in range(0, len(txt), 4096):
                await update.message.reply_text(txt[i:i+4096])
    except Exception as exc:
        logger.exception(f"Ошибка при обработке файла пользователя {user_id}")
        await update.message.reply_text(f"❌ Непредвиденная ошибка: {exc}")

# ───────  ЗАПУСК  ───────
def main():
    request = HTTPXRequest(connect_timeout=20, read_timeout=60, write_timeout=60, pool_timeout=10)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    logger.info("🤖 Бот запущен. Жду CSV-файлы…")
    app.run_polling()

if __name__ == "__main__":
    main()