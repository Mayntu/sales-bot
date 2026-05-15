"""Имя агента по user_id и безопасное отображение имени клиента в промпте."""

from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.domain.users.models import User


def pick_agent_name(user_id: uuid.UUID) -> str:
    names = get_settings().get_agent_names()
    if not names:
        return "Саша"
    index = int(user_id.int % len(names))
    return names[index]


def safe_client_display_name(user: User) -> str:
    """
    Имя клиента для блока КЛИЕНТ: не подставлять имя консультанта, если модель ошибочно
    записала его в user.name (частая путаница с «я Толкын» в истории).
    """
    agent = pick_agent_name(user.id)
    n = (user.name or "").strip()
    if not n:
        return "пока не знаем"
    if n.casefold() == agent.casefold():
        return "пока не знаем"
    return n


def client_first_name_for_followup(user: User) -> str:
    """Имя в приветствии follow-up (3d A); пусто если нет или совпадает с агентом."""
    agent = pick_agent_name(user.id)
    n = (user.name or "").strip()
    if not n or n.casefold() == agent.casefold():
        return ""
    return n
