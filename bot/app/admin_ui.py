"""
Панель администратора: inline-кнопки и пошаговые подсказки вместо длинных команд.

Колбэки начинаются с `adm:` (до 64 байт в Telegram).
"""

from __future__ import annotations

import html
import logging
import re
import secrets
from datetime import date
from typing import TYPE_CHECKING, Any

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from app.api_client import ApiClient

log = logging.getLogger(__name__)

CB_MAIN = "adm:main"
CB_DISC = "adm:d"
CB_DISC_SHOW = "adm:d:sh"
CB_DISC_CLEAR = "adm:d:cl"
CB_DISC_ADD = "adm:d:add"
CB_PRICE = "adm:p"
CB_TEMP = "adm:t"
CB_TEMP_SHOW = "adm:t:sh"
CB_TEMP_CLEAR_ASK = "adm:t:ca"
CB_TEMP_CLEAR_YES = "adm:t:cy"
CB_TEMP_ADD = "adm:t:add"
CB_STATS = "adm:s"
CB_HELP = "adm:i"
CB_NOOP = "adm:noop"

WIZ_DISCOUNT = "discount"
WIZ_PRICE = "price"
WIZ_TEMP = "temp_pipe"
WIZ_TEMP_FIELD = "temp_field"
WIZ_TEMP_FULL = "temp_full"


def _client(context: ContextTypes.DEFAULT_TYPE) -> ApiClient:
    return context.application.bot_data["api_client"]


def _admin_chats(context: ContextTypes.DEFAULT_TYPE) -> frozenset[int]:
    return context.application.bot_data.get("admin_chat_ids", frozenset())


def _wizard_key() -> str:
    return "admin_wizard"


def _clear_wizard(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_wizard_key(), None)


def _fmt_money(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _fmt_discounts_block(data: dict[str, Any]) -> str:
    d = data.get("date")
    items = data.get("discounts") or []
    lines = ["<b>Скидки дня</b>", f"Дата в конфиге: <code>{d or '—'}</code>", ""]
    if not items:
        lines.append("Сейчас список пуст — бот предложит базовые цены.")
    else:
        for it in items:
            mid = it.get("membership_id", "")
            price = it.get("discounted_price", "")
            label = it.get("label", "")
            lines.append(f"• <code>{html.escape(str(mid))}</code> — {_fmt_money(int(price))} ₸")
            lines.append(f"  <i>{html.escape(str(label))}</i>")
            lines.append("")
    return "\n".join(lines).strip()


def _fmt_temp_block(data: dict[str, Any]) -> str:
    items = data.get("items") or []
    lines = ["<b>Временные абонементы</b>", ""]
    if not items:
        lines.append("Список пуст.")
    else:
        for it in items:
            lines.append(
                f"• <b>{html.escape(str(it.get('name', '')))}</b> "
                f"<code>({html.escape(str(it.get('id', '')))})</code>\n"
                f"  {_fmt_money(int(it.get('base_price', 0)))} ₸ · "
                f"{html.escape(str(it.get('start_date', '')))} — {html.escape(str(it.get('end_date', '')))}"
            )
            if it.get("label"):
                lines.append(f"  <i>{html.escape(str(it['label']))}</i>")
            lines.append("")
    return "\n".join(lines).strip()


def _fmt_stats_block(data: dict[str, Any]) -> str:
    return (
        "<b>Статистика</b>\n\n"
        f"Пользователей в базе: <b>{data.get('users_total', 0)}</b>\n"
        f"Оплатили: <b>{data.get('paid', 0)}</b>\n"
        f"Конверсия: <b>{float(data.get('conversion', 0)) * 100:.2f}%</b>"
    )


def _instruction_text() -> str:
    return (
        "<b>Как пользоваться панелью</b>\n\n"
        "<b>Скидки дня</b> — у каждой строки кнопки «Изменить» и «Убрать»; "
        "«+ Добавить» — если позиции ещё нет в списке. Дата в конфиге обновляется при сохранении.\n\n"
        "<b>Базовая цена</b> — только для <u>постоянных</u> карт (Золотая / Серебро+ / Серебро). "
        "Офферы вроде 3+9 и 11+1 лежат во «Временных абонементах» (с датами); цену там можно "
        "поменять через тот же раздел или командой <code>/a_price</code> по id.\n\n"
        "<b>Временные абонементы</b> — «Изменить»: кнопки по полям (цена, даты, название, подпись) "
        "или одна строка из 5 полей без id; новый оффер «+ По шаблону» — 5 полей, id присваивается сам "
        "(или 6 полей с явным id для переноса из конфига).\n\n"
        "Старые команды <code>/a_help</code>, <code>/a_discount_set</code> и т.д. "
        "по-прежнему работают для автоматизации и скриптов."
    )


def _main_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("Скидки дня", callback_data=CB_DISC),
            InlineKeyboardButton("Базовые цены", callback_data=CB_PRICE),
        ],
        [
            InlineKeyboardButton("Временные абонементы", callback_data=CB_TEMP),
            InlineKeyboardButton("Статистика", callback_data=CB_STATS),
        ],
        [InlineKeyboardButton("Инструкция", callback_data=CB_HELP)],
    ]
    return InlineKeyboardMarkup(rows)


def _back_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton("« Главное меню", callback_data=CB_MAIN)]


def _temp_item_as_example_five(it: dict[str, Any]) -> str:
    """Пример строки из 5 полей (без id) — название|цена|даты|подпись."""

    def esc(s: str) -> str:
        return str(s).replace("|", " ").replace("\n", " ").strip()

    return "|".join(
        [
            esc(str(it.get("name", ""))),
            str(int(it.get("base_price", 0))),
            esc(str(it.get("start_date", ""))),
            esc(str(it.get("end_date", ""))),
            esc(str(it.get("label") or "")),
        ]
    )


def _kb_temp_field_wizard(tid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("« К полям правки", callback_data=f"adm:t:edit:{tid}")],
            [InlineKeyboardButton("« Временные абонементы", callback_data=CB_TEMP)],
            _back_row(),
        ]
    )


def _slug_from_display_name(name: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9]+", "_", name.strip())[:28].lower()
    raw = re.sub(r"_+", "_", raw).strip("_")
    if raw and re.fullmatch(r"[a-z0-9_]+", raw):
        return raw
    return ""


def _alloc_temp_id(name: str, used: set[str]) -> str:
    slug = _slug_from_display_name(name)
    if slug:
        cand = slug
        n = 0
        while cand in used:
            n += 1
            cand = f"{slug}_{n}"[:32]
        return cand
    for _ in range(40):
        cand = f"offer_{secrets.token_hex(3)}"
        if cand not in used:
            return cand
    return f"offer_{secrets.token_hex(8)}"


async def _patch_temporary_item(client: Any, item_id: str, **patch: Any) -> dict[str, Any]:
    cur = await client.admin_get_temporary()
    items: list[dict[str, Any]] = list(cur.get("items") or [])
    for i, it in enumerate(items):
        if it.get("id") == item_id:
            merged = {**it, **patch}
            items[i] = merged
            await client.admin_upsert_temporary(items)
            return merged
    raise ValueError("Временный абонемент не найден")


async def _show_temp_edit_menu(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, tid: str) -> None:
    _clear_wizard(context)
    try:
        tjson = await _client(context).admin_get_temporary()
    except Exception as e:
        await query.message.reply_text(f"Ошибка: {e}")
        return
    item = next((x for x in (tjson.get("items") or []) if x.get("id") == tid), None)
    if not item:
        await query.message.reply_text("Позиция не найдена")
        return
    rows = [
        [
            InlineKeyboardButton("Цена", callback_data=f"adm:t:f:{tid}:p"),
            InlineKeyboardButton("Период", callback_data=f"adm:t:f:{tid}:d"),
        ],
        [
            InlineKeyboardButton("Название", callback_data=f"adm:t:f:{tid}:n"),
            InlineKeyboardButton("Подпись", callback_data=f"adm:t:f:{tid}:l"),
        ],
        [InlineKeyboardButton("Всё одной строкой (5 полей)", callback_data=f"adm:t:f:{tid}:f")],
        [InlineKeyboardButton("« Временные абонементы", callback_data=CB_TEMP)],
        _back_row(),
    ]
    nm = html.escape(str(item.get("name", "")))
    ex = html.escape(_temp_item_as_example_five(item))
    await _safe_edit(
        query,
        f"<b>Правка</b> {nm}\n<code>{html.escape(tid)}</code> — служебный id, менять не нужно.\n\n"
        "Выберите поле. Состав «входит» и <code>access</code> — как в yaml; "
        "если нужно поменять их — правка файла.\n\n"
        f"Или «всё строкой» (без id): <code>{ex}</code>",
        reply_markup=InlineKeyboardMarkup(rows),
    )


def _discount_markup(djson: dict[str, Any]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("Обновить текст", callback_data=CB_DISC_SHOW),
            InlineKeyboardButton("Сбросить все", callback_data=CB_DISC_CLEAR),
        ],
        [InlineKeyboardButton("+ Добавить / заменить скидку", callback_data=CB_DISC_ADD)],
    ]
    for it in djson.get("discounts") or []:
        mid = it.get("membership_id", "")
        if not mid:
            continue
        rows.append(
            [
                InlineKeyboardButton(f"Изменить: {mid}", callback_data=f"adm:d:edit:{mid}"),
                InlineKeyboardButton(f"Убрать: {mid}", callback_data=f"adm:d:del:{mid}"),
            ]
        )
    rows.append(_back_row())
    return InlineKeyboardMarkup(rows)


def _catalog_permanent_cards(cat: dict[str, Any]) -> list[dict[str, Any]]:
    """Постоянные карты зала (не временные офферы)."""
    return list(cat.get("memberships") or [])


def _catalog_discount_targets(cat: dict[str, Any]) -> list[dict[str, Any]]:
    """Все id из каталога, на которые можно повесить скидку дня."""
    return (
        list(cat.get("memberships") or [])
        + list(cat.get("bundle_memberships") or [])
        + list(cat.get("temporary_memberships") or [])
    )


async def _safe_edit(
    query: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True
        )
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            # query.answer() уже вызван в admin_callback
            pass
        else:
            log.warning("edit_message_text: %s", e)
            await query.message.reply_text(
                text, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True
            )


async def cmd_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _clear_wizard(context)
    text = (
        "<b>Панель управления</b>\n\n"
        "Выберите раздел. Подсказки появятся после нажатия кнопок; "
        "полная инструкция — «Инструкция»."
    )
    await update.effective_message.reply_text(
        text,
        reply_markup=_main_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    msg = query.message
    if not msg or msg.chat.id not in _admin_chats(context):
        await query.answer()
        return
    data = query.data
    await query.answer()

    if data == CB_NOOP:
        return

    if data == CB_MAIN:
        _clear_wizard(context)
        await _safe_edit(
            query,
            "<b>Панель управления</b>\n\nВыберите раздел.",
            reply_markup=_main_keyboard(),
        )
        return

    if data == CB_HELP:
        kb = InlineKeyboardMarkup([_back_row()])
        await _safe_edit(query, _instruction_text(), reply_markup=kb)
        return

    if data == CB_STATS:
        try:
            raw = await _client(context).admin_stats()
        except Exception as e:
            log.exception("admin_stats")
            await _safe_edit(query, f"Ошибка API: <code>{e}</code>", reply_markup=InlineKeyboardMarkup([_back_row()]))
            return
        await _safe_edit(query, _fmt_stats_block(raw), reply_markup=InlineKeyboardMarkup([_back_row()]))
        return

    if data == CB_DISC:
        try:
            djson = await _client(context).admin_get_discounts()
        except Exception as e:
            log.exception("admin_get_discounts")
            await _safe_edit(query, f"Ошибка API: <code>{e}</code>", reply_markup=InlineKeyboardMarkup([_back_row()]))
            return
        await _safe_edit(query, _fmt_discounts_block(djson), reply_markup=_discount_markup(djson))
        return

    if data == CB_DISC_SHOW:
        try:
            djson = await _client(context).admin_get_discounts()
        except Exception as e:
            await query.message.reply_text(f"Ошибка: {e}")
            return
        await _safe_edit(query, _fmt_discounts_block(djson), reply_markup=_discount_markup(djson))
        return

    if data == CB_DISC_CLEAR:
        try:
            await _client(context).admin_set_discounts([])
            djson = await _client(context).admin_get_discounts()
        except Exception as e:
            log.exception("clear discounts")
            await query.message.reply_text(f"Ошибка: {e}")
            return
        await _safe_edit(query, _fmt_discounts_block(djson), reply_markup=_discount_markup(djson))
        return

    if data.startswith("adm:d:del:"):
        mid = data.removeprefix("adm:d:del:")
        try:
            cur = await _client(context).admin_get_discounts()
            discounts = [d for d in (cur.get("discounts") or []) if d.get("membership_id") != mid]
            await _client(context).admin_set_discounts(discounts)
            djson = await _client(context).admin_get_discounts()
        except Exception as e:
            log.exception("delete discount")
            await query.message.reply_text(f"Ошибка: {e}")
            return
        _clear_wizard(context)
        await _safe_edit(query, _fmt_discounts_block(djson), reply_markup=_discount_markup(djson))
        return

    if data.startswith("adm:d:edit:"):
        mid = data.removeprefix("adm:d:edit:")
        context.user_data[_wizard_key()] = {"kind": WIZ_DISCOUNT, "membership_id": mid}
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("« К скидкам дня", callback_data=CB_DISC)],
                _back_row(),
            ]
        )
        await _safe_edit(
            query,
            f"<b>Изменить скидку для</b> <code>{html.escape(mid)}</code>\n\n"
            "Пришлите <u>одним сообщением</u>: <code>цена_тг текст_для_клиента</code>\n"
            "Пример: <code>160000 Золотая −11% только сегодня</code>",
            reply_markup=kb,
        )
        return

    if data == CB_DISC_ADD:
        try:
            cat = await _client(context).admin_get_catalog()
        except Exception as e:
            await query.message.reply_text(f"Ошибка каталога: {e}")
            return
        buttons: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []
        for m in _catalog_discount_targets(cat):
            mid = m.get("id")
            if not mid:
                continue
            label = str(m.get("name", mid))[:18]
            row.append(InlineKeyboardButton(label, callback_data=f"adm:d:pick:{mid}"))
            if len(row) >= 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append(_back_row())
        await _safe_edit(
            query,
            "<b>Скидка дня — на какую позицию?</b>\n\n"
            "Постоянные карты и активные временные офферы (3+9, 11+1, Spring Cut и т.д.), если на них нужна акция на сегодня.\n"
            "Нажмите кнопку — затем одним сообщением пришлите цену и текст акции, например:\n"
            "<code>160000 Золотая −11% только сегодня</code>",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("adm:d:pick:"):
        mid = data.removeprefix("adm:d:pick:")
        context.user_data[_wizard_key()] = {"kind": WIZ_DISCOUNT, "membership_id": mid}
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("« К выбору карты", callback_data=CB_DISC_ADD)],
                _back_row(),
            ]
        )
        await _safe_edit(
            query,
            f"<b>Карта:</b> <code>{html.escape(mid)}</code>\n\n"
            "Пришлите <u>одним сообщением</u>: <code>цена_тг текст_для_клиента</code>\n"
            "Пример: <code>160000 Золотая −11% только сегодня</code>",
            reply_markup=kb,
        )
        return

    if data == CB_PRICE:
        try:
            cat = await _client(context).admin_get_catalog()
        except Exception as e:
            await query.message.reply_text(f"Ошибка: {e}")
            return
        buttons = []
        row = []
        for m in _catalog_permanent_cards(cat):
            mid = m.get("id")
            if not mid:
                continue
            price = m.get("base_price", "")
            title = f"{mid} · {_fmt_money(int(price))}"
            row.append(InlineKeyboardButton(title, callback_data=f"adm:p:pick:{mid}"))
            if len(row) >= 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append(_back_row())
        await _safe_edit(
            query,
            "<b>Базовая цена в yaml</b>\n\n"
            "Только постоянные карты (временные офферы — в другом разделе панели).\n"
            "Выберите карту, затем пришлите одним сообщением новую целую сумму в тенге.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("adm:p:pick:"):
        mid = data.removeprefix("adm:p:pick:")
        context.user_data[_wizard_key()] = {"kind": WIZ_PRICE, "membership_id": mid}
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("« К списку карт", callback_data=CB_PRICE)],
                _back_row(),
            ]
        )
        await _safe_edit(
            query,
            f"<b>Карта:</b> <code>{html.escape(mid)}</code>\n\n"
            "Пришлите новую цену одним числом, например: <code>175000</code>",
            reply_markup=kb,
        )
        return

    if data == CB_TEMP:
        await _render_temp_menu(query, context)
        return

    if data == CB_TEMP_SHOW:
        await _render_temp_menu(query, context)
        return

    if data == CB_TEMP_CLEAR_ASK:
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Да, удалить все", callback_data=CB_TEMP_CLEAR_YES),
                    InlineKeyboardButton("Отмена", callback_data=CB_TEMP),
                ]
            ]
        )
        await _safe_edit(
            query,
            "<b>Удалить все временные абонементы?</b>\n\nЭто действие сразу перезапишет список в yaml.",
            reply_markup=kb,
        )
        return

    if data == CB_TEMP_CLEAR_YES:
        try:
            await _client(context).admin_upsert_temporary([])
        except Exception as e:
            log.exception("clear temp")
            await query.message.reply_text(f"Ошибка: {e}")
            return
        await _render_temp_menu(query, context)
        return

    if data == CB_TEMP_ADD:
        try:
            cat = await _client(context).admin_get_catalog()
        except Exception as e:
            await query.message.reply_text(f"Ошибка: {e}")
            return
        buttons = []
        row = []
        for m in _catalog_permanent_cards(cat):
            mid = m.get("id")
            if not mid:
                continue
            row.append(InlineKeyboardButton(mid[:20], callback_data=f"adm:t:tmpl:{mid}"))
            if len(row) >= 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("« Назад", callback_data=CB_TEMP)])
        buttons.append(_back_row())
        await _safe_edit(
            query,
            "<b>Шаблон постоянной карты</b>\n\n"
            "Здесь только золото/серебро как шаблон доступа и плюш; готовые офферы 3+9/11+1 — в списке временных.\n"
            "Выберите карту — скопируем <code>access</code> и список <code>includes</code>.\n\n"
            "Затем одним сообщением — <b>обычно 5 полей</b> (id бот присвоит сам из названия или "
            "<code>offer_xxx</code>):\n"
            "<code>название|цена|дата_нач|дата_конец|подпись</code>\n\n"
            "Для переноса из старого конфига можно одной строкой <b>6 полей</b> с явным "
            "<code>id|…</code> (латиница и _).\n\n"
            "Пример (5 полей):\n"
            "<code>Новогодний оффер|99000|2026-12-20|2026-12-31|Только до НГ</code>",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("adm:t:tmpl:"):
        mid = data.removeprefix("adm:t:tmpl:")
        try:
            cat = await _client(context).admin_get_catalog()
        except Exception as e:
            await query.message.reply_text(f"Ошибка: {e}")
            return
        template: dict[str, Any] | None = None
        for m in _catalog_permanent_cards(cat):
            if m.get("id") == mid:
                template = m
                break
        if not template:
            await query.message.reply_text("Шаблон не найден")
            return
        context.user_data[_wizard_key()] = {"kind": WIZ_TEMP, "template": template}
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("« Другой шаблон", callback_data=CB_TEMP_ADD)],
                [InlineKeyboardButton("« Временные", callback_data=CB_TEMP)],
                _back_row(),
            ]
        )
        await _safe_edit(
            query,
            f"<b>Шаблон:</b> <code>{html.escape(mid)}</code> — {html.escape(str(template.get('name', '')))}\n\n"
            "Обычно пришлите <b>5 полей</b> через <code>|</code> (без id — сгенерируем сами):\n"
            "<code>название|цена|YYYY-MM-DD|YYYY-MM-DD|подпись</code>\n\n"
            "Либо <b>6 полей</b> с явным id: <code>id|название|цена|…|подпись</code>",
            reply_markup=kb,
        )
        return

    m_field = re.fullmatch(r"adm:t:f:(.+):([pndlf])", data)
    if m_field:
        tid, code = m_field.group(1), m_field.group(2)
        try:
            tjson = await _client(context).admin_get_temporary()
        except Exception as e:
            await query.message.reply_text(f"Ошибка: {e}")
            return
        item = next((x for x in (tjson.get("items") or []) if x.get("id") == tid), None)
        if not item:
            await query.message.reply_text("Позиция не найдена")
            return
        kb = _kb_temp_field_wizard(tid)
        if code == "p":
            context.user_data[_wizard_key()] = {"kind": WIZ_TEMP_FIELD, "item_id": tid, "field": "price"}
            await _safe_edit(
                query,
                f"<b>Цена</b> — <code>{html.escape(tid)}</code>\n\n"
                "Одним числом в тенге, например <code>149000</code>",
                reply_markup=kb,
            )
        elif code == "d":
            context.user_data[_wizard_key()] = {"kind": WIZ_TEMP_FIELD, "item_id": tid, "field": "dates"}
            await _safe_edit(
                query,
                f"<b>Период</b> — <code>{html.escape(tid)}</code>\n\n"
                "Две даты через пробел: <code>2026-04-01 2026-06-30</code>",
                reply_markup=kb,
            )
        elif code == "n":
            context.user_data[_wizard_key()] = {"kind": WIZ_TEMP_FIELD, "item_id": tid, "field": "name"}
            await _safe_edit(
                query,
                f"<b>Название</b> — <code>{html.escape(tid)}</code>\n\n"
                "Одним сообщением — как показывать клиенту (например <code>11+1</code>).",
                reply_markup=kb,
            )
        elif code == "l":
            context.user_data[_wizard_key()] = {"kind": WIZ_TEMP_FIELD, "item_id": tid, "field": "label"}
            await _safe_edit(
                query,
                f"<b>Подпись</b> — <code>{html.escape(tid)}</code>\n\n"
                "Короткий текст оффера одним сообщением.",
                reply_markup=kb,
            )
        elif code == "f":
            context.user_data[_wizard_key()] = {"kind": WIZ_TEMP_FULL, "item": dict(item)}
            ex = html.escape(_temp_item_as_example_five(item))
            await _safe_edit(
                query,
                f"<b>Все поля строкой</b> — <code>{html.escape(tid)}</code>\n\n"
                "Без id — пришлите <b>5 полей</b> через <code>|</code>:\n"
                "<code>название|цена|дата_нач|дата_конец|подпись</code>\n\n"
                f"Пример (скопируйте и поправьте):\n<code>{ex}</code>",
                reply_markup=kb,
            )
        return

    if data.startswith("adm:t:edit:"):
        tid = data.removeprefix("adm:t:edit:")
        await _show_temp_edit_menu(query, context, tid)
        return

    if data.startswith("adm:t:del:"):
        tid = data.removeprefix("adm:t:del:")
        try:
            cur = await _client(context).admin_get_temporary()
            items = [x for x in (cur.get("items") or []) if x.get("id") != tid]
            await _client(context).admin_upsert_temporary(items)
        except Exception as e:
            log.exception("delete temp")
            await query.message.reply_text(f"Ошибка: {e}")
            return
        await _render_temp_menu(query, context)
        return


async def _render_temp_menu(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        tjson = await _client(context).admin_get_temporary()
    except Exception as e:
        await query.message.reply_text(f"Ошибка: {e}")
        return
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("Обновить", callback_data=CB_TEMP_SHOW),
            InlineKeyboardButton("+ По шаблону", callback_data=CB_TEMP_ADD),
        ],
        [InlineKeyboardButton("Удалить все…", callback_data=CB_TEMP_CLEAR_ASK)],
    ]
    for it in tjson.get("items") or []:
        tid = it.get("id", "")
        if not tid:
            continue
        rows.append(
            [
                InlineKeyboardButton(f"Изменить: {tid}"[:30], callback_data=f"adm:t:edit:{tid}"),
                InlineKeyboardButton(f"Удалить: {tid}"[:30], callback_data=f"adm:t:del:{tid}"),
            ]
        )
    rows.append(_back_row())
    await _safe_edit(query, _fmt_temp_block(tjson), reply_markup=InlineKeyboardMarkup(rows))


async def try_consume_admin_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Если активен мастер настройки — обработать текст и не слать в чат-API."""
    msg = update.effective_message
    if not msg or not msg.text or msg.text.startswith("/"):
        return False
    chat_id = msg.chat_id
    if chat_id not in _admin_chats(context):
        return False
    st = context.user_data.get(_wizard_key())
    if not st:
        return False
    client = _client(context)
    text = msg.text.strip()

    try:
        if st["kind"] == WIZ_DISCOUNT:
            parts = text.split(None, 1)
            if len(parts) < 2:
                await msg.reply_text("Нужно: цена и текст. Пример: 160000 Скидка 11%")
                return True
            price_s, label = parts[0], parts[1]
            price = int(price_s)
            mid = st["membership_id"]
            cur = await client.admin_get_discounts()
            discounts: list[dict[str, Any]] = list(cur.get("discounts") or [])
            new_item = {"membership_id": mid, "discounted_price": price, "label": label}
            replaced = False
            for i, d in enumerate(discounts):
                if d.get("membership_id") == mid:
                    discounts[i] = new_item
                    replaced = True
                    break
            if not replaced:
                discounts.append(new_item)
            await client.admin_set_discounts(discounts)
            action = "обновлена" if replaced else "добавлена"
            await msg.reply_text(
                f"Скидка для <code>{html.escape(mid)}</code> {action}.\n"
                f"Цена: {_fmt_money(price)} ₸\n"
                f"Текст: {html.escape(label)}",
                parse_mode="HTML",
            )
            _clear_wizard(context)
            return True

        if st["kind"] == WIZ_PRICE:
            if not text.isdigit():
                await msg.reply_text("Пришлите одно целое число — цену в тенге.")
                return True
            price = int(text)
            mid = st["membership_id"]
            await client.admin_set_price(mid, price)
            await msg.reply_text(
                f"Базовая цена <code>{html.escape(mid)}</code> → {_fmt_money(price)} ₸", parse_mode="HTML"
            )
            _clear_wizard(context)
            return True

        if st["kind"] == WIZ_TEMP:
            template = st.get("template") or {}
            fields = [p.strip() for p in text.split("|")]
            cur = await client.admin_get_temporary()
            items = list(cur.get("items") or [])
            used = {str(x.get("id")) for x in items if x.get("id")}

            if len(fields) == 5:
                name, price_s, start_s, end_s, label = fields
                tid = _alloc_temp_id(name, used)
                price = int(price_s.replace(" ", "").replace("\u00a0", ""))
                date.fromisoformat(start_s)
                date.fromisoformat(end_s)
                new_item = {
                    "id": tid,
                    "name": name,
                    "base_price": price,
                    "start_date": start_s,
                    "end_date": end_s,
                    "access": template.get("access"),
                    "includes": list(template.get("includes") or []),
                    "label": label or None,
                }
                items.append(new_item)
                await client.admin_upsert_temporary(items)
                await msg.reply_text(
                    f"Добавлено: <code>{html.escape(tid)}</code>\n"
                    f"{html.escape(name)} — {_fmt_money(price)} ₸ ({html.escape(start_s)}…{html.escape(end_s)})",
                    parse_mode="HTML",
                )
                _clear_wizard(context)
                return True

            if len(fields) == 6:
                tid, name, price_s, start_s, end_s, label = fields
                if not re.fullmatch(r"[a-z0-9_]+", tid):
                    await msg.reply_text(
                        "Поле <code>id</code>: только латиница, цифры и _. Или используйте 5 полей без id.",
                        parse_mode="HTML",
                    )
                    return True
                price = int(price_s.replace(" ", "").replace("\u00a0", ""))
                date.fromisoformat(start_s)
                date.fromisoformat(end_s)
                new_item = {
                    "id": tid,
                    "name": name,
                    "base_price": price,
                    "start_date": start_s,
                    "end_date": end_s,
                    "access": template.get("access"),
                    "includes": list(template.get("includes") or []),
                    "label": label or None,
                }
                replaced = False
                for i, it in enumerate(items):
                    if it.get("id") == tid:
                        items[i] = new_item
                        replaced = True
                        break
                if not replaced:
                    items.append(new_item)
                await client.admin_upsert_temporary(items)
                await msg.reply_text(
                    f"{'Обновлено' if replaced else 'Добавлено'}: <code>{html.escape(tid)}</code>\n"
                    f"{html.escape(name)} — {_fmt_money(price)} ₸ ({html.escape(start_s)}…{html.escape(end_s)})",
                    parse_mode="HTML",
                )
                _clear_wizard(context)
                return True

            await msg.reply_text(
                "Нужно <b>5 полей</b> (без id — id присвоит бот) или <b>6 полей</b> (с явным id):\n"
                "<code>название|цена|дата_нач|дата_конец|подпись</code>\n"
                "или <code>id|название|цена|дата_нач|дата_конец|подпись</code>",
                parse_mode="HTML",
            )
            return True

        if st["kind"] == WIZ_TEMP_FULL:
            item = st.get("item") or {}
            oid = item.get("id")
            if not oid:
                _clear_wizard(context)
                return True
            fields = [p.strip() for p in text.split("|")]
            if len(fields) != 5:
                await msg.reply_text(
                    "Нужно ровно 5 полей через <code>|</code> (без id):\n"
                    "<code>название|цена|дата_нач|дата_конец|подпись</code>",
                    parse_mode="HTML",
                )
                return True
            name, price_s, start_s, end_s, label = fields
            price = int(price_s.replace(" ", "").replace("\u00a0", ""))
            date.fromisoformat(start_s)
            date.fromisoformat(end_s)
            await _patch_temporary_item(
                client,
                str(oid),
                name=name,
                base_price=price,
                start_date=start_s,
                end_date=end_s,
                label=label or None,
            )
            await msg.reply_text(
                f"Обновлено <code>{html.escape(str(oid))}</code>.\n"
                f"{html.escape(name)} — {_fmt_money(price)} ₸ ({html.escape(start_s)}…{html.escape(end_s)})",
                parse_mode="HTML",
            )
            _clear_wizard(context)
            return True

        if st["kind"] == WIZ_TEMP_FIELD:
            tid = str(st.get("item_id") or "")
            field = st.get("field")
            if not tid or field not in ("price", "dates", "name", "label"):
                _clear_wizard(context)
                return True
            if field == "price":
                digits = text.replace(" ", "").replace("\u00a0", "")
                if not digits.isdigit():
                    await msg.reply_text("Одно целое число — цена в тенге.")
                    return True
                await _patch_temporary_item(client, tid, base_price=int(digits))
            elif field == "dates":
                parts = text.split()
                if len(parts) != 2:
                    await msg.reply_text("Две даты через пробел: <code>2026-04-01 2026-06-30</code>", parse_mode="HTML")
                    return True
                start_s, end_s = parts[0], parts[1]
                date.fromisoformat(start_s)
                date.fromisoformat(end_s)
                await _patch_temporary_item(client, tid, start_date=start_s, end_date=end_s)
            elif field == "name":
                await _patch_temporary_item(client, tid, name=text)
            else:
                await _patch_temporary_item(client, tid, label=text or None)
            await msg.reply_text(
                f"Сохранено (<code>{html.escape(tid)}</code>). Откройте снова «Временные абонементы», чтобы проверить.",
                parse_mode="HTML",
            )
            _clear_wizard(context)
            return True

    except ValueError:
        await msg.reply_text("Не получилось разобрать число или дату. Проверьте формат.")
        return True
    except Exception as e:
        log.exception("wizard")
        await msg.reply_text(f"Ошибка: {e}")
        _clear_wizard(context)
        return True

    return False
