from pydantic import BaseModel, HttpUrl


class PaymentLinkBody(BaseModel):
    telegram_chat_id: int
    payment_url: str
