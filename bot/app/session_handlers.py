"""Админ: /refresh, /state, /followup_now."""

import logging

import httpx
from telegram import Update
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)


async def cmd_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return
    client = context.application.bot_data["api_client"]
    try:
        data = await client.admin_refresh_user(chat.id)
    except httpx.HTTPStatusError:
        await msg.reply_text("Не вышло: проверь ADMIN_SECRET и что API знает ADMIN_CHAT_IDS (как в .env у бота).")
        return
    except Exception as exc:
        log.exception("admin_refresh_user")
        await msg.reply_text(f"Ошибка: {exc}")
        return
    if data.get("deleted"):
        await msg.reply_text("Готово: запись удалена из БД. Напиши боту снова — будешь как новый клиент.")
    else:
        await msg.reply_text("В БД тебя ещё не было — уже «чисто». Просто пиши боту.")


async def cmd_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return
    client = context.application.bot_data["api_client"]
    try:
        data = await client.admin_user_state(chat.id)
    except httpx.HTTPStatusError:
        await msg.reply_text("Не вышло: ADMIN_SECRET или ADMIN_CHAT_IDS на API.")
        return
    except Exception as exc:
        log.exception("admin_user_state")
        await msg.reply_text(f"Ошибка: {exc}")
        return
    if not data.get("exists"):
        await msg.reply_text("<b>В БД нет строки пользователя.</b>", parse_mode="HTML")
        return
    lines = [
        "<b>Текущее состояние</b>",
        f"state: <code>{data.get('state')}</code>",
        f"имя: <code>{data.get('name') or 'null'}</code>",
        f"цель: <code>{data.get('goal') or 'null'}</code>",
        f"followup_count: <code>{data.get('followup_count')}</code>",
        f"сообщений в истории: <code>{data.get('message_count')}</code>",
    ]
    await msg.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_followup_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return
    client = context.application.bot_data["api_client"]
    try:
        data = await client.admin_followup_now(chat.id)
    except httpx.HTTPStatusError:
        await msg.reply_text("Не вышло: ADMIN_SECRET или ADMIN_CHAT_IDS на API.")
        return
    except Exception as exc:
        log.exception("admin_followup_now")
        await msg.reply_text(f"Ошибка: {exc}")
        return
    if data.get("user_missing"):
        await msg.reply_text("Нет строки пользователя в БД. Напиши боту сообщение или /start.")
        return
    if data.get("sent"):
        mt = data.get("message_type") or "?"
        await msg.reply_text(f"Follow-up отправлен: {mt} (2h/5h/1d/3d/7d/14d)")
        return
    await msg.reply_text(f"Нет активных follow-up задач. Состояние: {data.get('user_state')}")
