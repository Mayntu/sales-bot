"""
Серверный выбор ветки follow-up (A/B/S) и итоговый текст сообщения.
Текст целиком собирается здесь — без LLM, чтобы не путать этапы и не дублировать «чатовые» простыни.
"""

from __future__ import annotations

import re
from typing import Literal

from app.ai.agent_identity import client_first_name_for_followup
from app.ai.club_context import ClubContext
from app.domain.users.models import User

FollowupVariant = Literal["A", "B", "S"]

_UNKNOWN_GOAL = frozenset(
    {
        "",
        "пока не выяснена",
        "пока не выяснена.",
        "не знаю",
        "неизвестно",
        "уточняется",
        "n/a",
        "na",
        "null",
    }
)

_PRICE_OBJECTION_RE = re.compile(
    r"дорог(?:о|овато)?|не\s*потян|не\s*готов\s*плат|слишком\s*цен|много\s*за|"
    r"не\s*по\s*карману|не\s*устроил[аио]?\s*цен|не\s*устроила\s*цена|"
    r"не\s*по\s*кошельку|копейк|жаба\s*давит|не\s*осил",
    re.IGNORECASE | re.UNICODE,
)


def goal_is_concrete(user: User) -> bool:
    g = (user.goal or "").strip().lower()
    if len(g) < 6:
        return False
    if g in _UNKNOWN_GOAL:
        return False
    return True


def dialog_has_price_objection(dialog: list[dict]) -> bool:
    for m in dialog:
        if m.get("role") != "user":
            continue
        text = m.get("content") or ""
        if _PRICE_OBJECTION_RE.search(text):
            return True
    return False


def resolve_followup_variant(
    followup_type: str,
    user: User,
    dialog: list[dict],
    club: ClubContext,
) -> FollowupVariant:
    if followup_type in ("7d", "14d"):
        return "S"
    if followup_type == "2h":
        return "A" if goal_is_concrete(user) else "B"
    if followup_type == "5h":
        if dialog_has_price_objection(dialog) and club.followup_anchor_card() is not None:
            return "A"
        return "B"
    if followup_type == "1d":
        return "A" if goal_is_concrete(user) else "B"
    if followup_type == "3d":
        if club.has_promo_for_followup_3d() and club.followup_promo_one_liner():
            return "A"
        return "B"
    return "B"


def _fmt_tg(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _goal_phrase(user: User) -> str:
    g = (user.goal or "").strip()
    if g and g.lower() not in _UNKNOWN_GOAL:
        return g[:180]
    return "того, о чём ты писал"


def build_followup_draft(
    user: User,
    club: ClubContext,
    followup_type: str,
    variant: FollowupVariant,
) -> str:
    anchor = club.followup_anchor_card()
    goal = _goal_phrase(user)
    first = client_first_name_for_followup(user)

    if followup_type == "2h":
        if variant == "A":
            return (
                f"Кстати, по поводу {goal} — у нас как раз есть кое-что интересное.\n"
                f"Хочешь расскажу подробнее? 😊"
            )
        return (
            "Если остались вопросы — я здесь, отвечу быстро 🙂\n"
            "Что больше интересует — залы, цены или что-то конкретное?"
        )

    if followup_type == "5h":
        if variant == "A" and anchor:
            return (
                "Смотри, вот как это выглядит по-другому —\n"
                f"{anchor.display_name} в рассрочку это {_fmt_tg(anchor.per_day_tg)} тг в день, "
                f"меньше чашки кофе ☕\n"
                "Попробуем оформить?"
            )
        return (
            "День пролетит — и снова откладывать 😅\n"
            "Один вопрос: что реально останавливает прямо сейчас?"
        )

    if followup_type == "1d":
        if variant == "A":
            return (
                f"Прошли сутки — а {goal} никуда не делась, правда? 💪\n"
                "Давай так: просто приходи посмотреть зал, первая тренировка 5000 тг.\n"
                "Посмотришь своими глазами — и всё станет понятно."
            )
        return (
            "Слушай, ты же не просто так написал тогда 🙂\n"
            "Что-то зацепило — что именно? Давай разберёмся вместе."
        )

    if followup_type == "3d":
        promo = club.followup_promo_one_liner()
        if variant == "A" and promo:
            open_ = f"{first}, " if first else ""
            return (
                f"{open_}три дня думаешь — значит интерес точно есть 🔥\n"
                f"Сегодня кстати есть {promo} — это реально выгодно.\n"
                "Скажи да или нет — я пойму в любом случае."
            )
        return (
            "Три дня прошло — давай честно 🙂\n"
            "Что главный стоп? Цена, время, или что-то другое?\n"
            "Подберём вариант который зайдёт."
        )

    if followup_type == "7d":
        if anchor:
            xm = _fmt_tg(anchor.monthly_tg)
            return (
                "Неделю думаешь — уважаю 😄\n"
                "Последний раз спрошу: что мешает начать?\n"
                f"Если цена — есть рассрочка порядка {xm} тг в месяц.\n"
                "Если что-то другое — скажи, найдём решение."
            )
        return (
            "Неделю думаешь — уважаю 😄\n"
            "Последний раз спрошу: что мешает начать?\n"
            "Если цена — напиши, подскажу по рассрочке и вариантам.\n"
            "Если что-то другое — скажи, найдём решение."
        )

    if followup_type == "14d":
        return (
            "Последний раз пишу — не хочу надоедать 🙂\n"
            "Если надумаешь — просто напиши сюда, всегда помогу.\n"
            "Удачи и здоровья!"
        )

    # неизвестный тип — безопасный короткий пинг
    return (
        "Напоминаю про себя — если остались вопросы по залу или абонементам, напиши 🙂\n"
        "Что сейчас важнее разобрать?"
    )


def compose_followup_message(user: User, club: ClubContext, followup_type: str, dialog: list[dict]) -> str:
    variant = resolve_followup_variant(followup_type, user, dialog, club)
    return build_followup_draft(user, club, followup_type, variant)
