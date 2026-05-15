"""Админ-команды в Telegram (только для chat_id из ADMIN_CHAT_IDS)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from app.api_client import ApiClient


def _client(context: ContextTypes.DEFAULT_TYPE) -> ApiClient:
    return context.application.bot_data["api_client"]


def _parse_discount_line(rest: str) -> list[dict]:
    """Формат: `id цена лейбл; id2 цена2 лейбл2` (лейбл — всё после второго пробела)."""
    items: list[dict] = []
    for chunk in rest.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(None, 2)
        if len(parts) < 3:
            raise ValueError(f"Неверный фрагмент: «{chunk}». Нужно: id цена лейбл")
        mid, price_s, label = parts[0], parts[1], parts[2]
        items.append({"membership_id": mid, "discounted_price": int(price_s), "label": label})
    if not items:
        raise ValueError("Пустой список скидок")
    return items


async def cmd_a_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Удобная панель с кнопками: /admin\n\n"
        "Отладка диалога (только админский chat_id в .env):\n"
        "/refresh — удалить свою запись из БД; следующее сообщение = новый клиент\n"
        "/state — state, имя, цель, followup_count, число сообщений в истории\n"
        "/followup_now — немедленно следующий pending follow-up (демо)\n\n"
        "Текстовые команды (меняют club_info.yaml без перезапуска):\n\n"
        "/a_discounts — текущие скидки дня (JSON)\n"
        "/a_discount_set id цена лейбл; id2 цена2 лейбл2 — задать скидки на сегодня (заменяет список)\n"
        "/a_discount_clear — убрать все скидки дня\n"
        "/a_price <membership_id> <новая_цена> — базовая цена в yaml\n"
        "/a_temp — временные абонементы (JSON)\n"
        "/a_stats — лиды / оплаты (JSON)\n\n"
        "Пример одной командой:\n"
        "/a_discount_set gold 160000 Золотая -11% только сегодня; silver_plus 110000 Серебро+ акция"
    )


async def cmd_a_discounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await _client(context).admin_get_discounts()
    await update.effective_message.reply_text(json.dumps(data, ensure_ascii=False, indent=2))


async def cmd_a_discount_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""
    prefix = "/a_discount_set"
    if not text.startswith(prefix):
        return
    rest = text[len(prefix) :].strip()
    if not rest:
        await update.effective_message.reply_text(
            "Формат: /a_discount_set id цена лейбл; id2 цена2 лейбл2"
        )
        return
    try:
        items = _parse_discount_line(rest)
    except ValueError as e:
        await update.effective_message.reply_text(str(e))
        return
    res = await _client(context).admin_set_discounts(items)
    await update.effective_message.reply_text(json.dumps(res, ensure_ascii=False))


async def cmd_a_discount_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    res = await _client(context).admin_set_discounts([])
    await update.effective_message.reply_text(json.dumps(res, ensure_ascii=False))


async def cmd_a_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.effective_message.reply_text("Формат: /a_price gold 180000")
        return
    mid, price_s = context.args[0], context.args[1]
    try:
        price = int(price_s)
    except ValueError:
        await update.effective_message.reply_text("Цена должна быть числом")
        return
    res = await _client(context).admin_set_price(mid, price)
    await update.effective_message.reply_text(json.dumps(res, ensure_ascii=False))


async def cmd_a_temp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await _client(context).admin_get_temporary()
    await update.effective_message.reply_text(json.dumps(data, ensure_ascii=False, indent=2))


async def cmd_a_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await _client(context).admin_stats()
    await update.effective_message.reply_text(json.dumps(data, ensure_ascii=False, indent=2))
