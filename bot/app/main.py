import logging
import os
import sys

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.admin_handlers import (
    cmd_a_discount_clear,
    cmd_a_discount_set,
    cmd_a_discounts,
    cmd_a_help,
    cmd_a_price,
    cmd_a_stats,
    cmd_a_temp,
)
from app.admin_ui import admin_callback, cmd_admin_panel
from app.api_client import ApiClient
from app.handlers import handle_message
from app.session_handlers import cmd_followup_now, cmd_refresh, cmd_state

log = logging.getLogger(__name__)


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = ""
    api_internal_url: str = "http://api:8000"
    admin_secret: str = ""
    admin_chat_ids: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_CHAT_IDS", "ADMIN_TELEGRAM_CHAT_IDS"),
    )


def _parse_admin_chat_ids(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return tuple(out)


def build_app() -> Application:
    s = BotSettings()
    app = Application.builder().token(s.telegram_bot_token).build()
    app.bot_data["api_client"] = ApiClient(s.api_internal_url, admin_secret=s.admin_secret)

    admin_chats = _parse_admin_chat_ids(s.admin_chat_ids)
    if admin_chats and not s.admin_secret:
        log.warning("Задан ADMIN_CHAT_IDS, но пустой ADMIN_SECRET — админ-команды в Telegram отключены")
    if admin_chats and s.admin_secret:
        af = filters.Chat(chat_id=admin_chats)
        app.bot_data["admin_chat_ids"] = frozenset(admin_chats)
        app.add_handler(CommandHandler("admin", cmd_admin_panel, filters=af))
        app.add_handler(CommandHandler("a_help", cmd_a_help, filters=af))
        app.add_handler(CommandHandler("a_discounts", cmd_a_discounts, filters=af))
        app.add_handler(CommandHandler("a_discount_set", cmd_a_discount_set, filters=af))
        app.add_handler(CommandHandler("a_discount_clear", cmd_a_discount_clear, filters=af))
        app.add_handler(CommandHandler("a_price", cmd_a_price, filters=af))
        app.add_handler(CommandHandler("a_temp", cmd_a_temp, filters=af))
        app.add_handler(CommandHandler("a_stats", cmd_a_stats, filters=af))
        app.add_handler(CommandHandler("refresh", cmd_refresh, filters=af))
        app.add_handler(CommandHandler("state", cmd_state, filters=af))
        app.add_handler(CommandHandler("followup_now", cmd_followup_now, filters=af))
        # CallbackQueryHandler в PTB не принимает filters= — проверка чата в admin_callback
        app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^adm:", block=True))

    app.add_handler(CommandHandler("start", handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


def _configure_logging() -> None:
    level_name = os.getenv("BOT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("telegram").setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def run() -> None:
    _configure_logging()
    log.info("Starting Telegram bot (polling)…")
    app = build_app()
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    run()
