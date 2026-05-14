from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    telegram_chat_id: int = Field(..., description="Telegram chat_id of the user")
    message_text: str = Field(..., min_length=1, max_length=4096)


class ChatOut(BaseModel):
    reply_text: str
    state: str
    actions: list[str]
