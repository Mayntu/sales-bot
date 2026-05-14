from telegram import Update
from telegram.ext import ContextTypes

from app.admin_ui import try_consume_admin_wizard
from app.api_client import ApiClient


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message or not update.message.text:
        return
    if await try_consume_admin_wizard(update, context):
        return
    client: ApiClient = context.application.bot_data["api_client"]
    data = await client.send_message(update.effective_chat.id, update.message.text)
    await update.message.reply_text(data["reply_text"])
