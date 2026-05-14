"""
Manager controller — sends a payment link to a user via Telegram.

The Telegram message is dispatched to the dedicated `notifications` Celery queue
so the HTTP response returns immediately without waiting for Telegram API.
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.manager.schemas import PaymentLinkBody
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.domain.conversations.models import MessageRole
from app.domain.conversations.repo import ConversationsRepo
from app.domain.users.models import UserState
from app.domain.users.repo import UsersRepo

router = APIRouter(prefix="/manager", tags=["manager"])


def require_manager(x_manager_secret: str | None = Header(default=None, alias="X-Manager-Secret")) -> None:
    s = get_settings()
    if not s.manager_api_secret or x_manager_secret != s.manager_api_secret:
        raise UnauthorizedError()


@router.post("/send-payment-link", dependencies=[Depends(require_manager)])
async def send_payment_link(
    body: PaymentLinkBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await UsersRepo(db).get_by_chat_id(body.telegram_chat_id)
    if not user:
        raise NotFoundError("User not found")

    user.state = UserState.WAITING_PAYMENT
    text = f"Держи ссылку на оплату:\n\n{body.payment_url}"
    await ConversationsRepo(db).add_message(user.id, MessageRole.assistant, text)
    await db.commit()

    # Dispatch Telegram send to the notifications queue — non-blocking
    from app.tasks.notifications import send_telegram_task  # local import avoids circular

    send_telegram_task.apply_async(
        args=[user.telegram_chat_id, text],
        queue="notifications",
    )

    return {"ok": True}
