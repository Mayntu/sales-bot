"""
club_context.py — загрузка и форматирование данных клуба для AI-промпта.

to_prompt_text() возвращает структурированный текст, удобный для модели:
каждый абонемент — единый блок со всеми свойствами, хуки идут отдельным
приоритетным разделом, цена разбита на день и на рассрочку.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)


# ─── Pydantic модели ────────────────────────────────────────────────────────

class DailyDiscount(BaseModel):
    membership_id: str
    discounted_price: int
    label: str


class DailyDiscounts(BaseModel):
    """valid_on маппится из YAML-поля `date` — нельзя называть поле `date`, затеняет тип."""

    model_config = ConfigDict(populate_by_name=True)

    valid_on: date | None = Field(default=None, alias="date")
    discounts: list[DailyDiscount] = Field(default_factory=list)


class ClubContext(BaseModel):
    gym_name: str
    raw: dict
    daily_discounts: DailyDiscounts = DailyDiscounts()

    # ── публичный метод для промпта ──────────────────────────────────────────

    def to_prompt_text(self) -> str:
        parts: list[str] = []

        parts.append(self._section_memberships())
        parts.append(self._section_bundles())

        temp = self._section_temporary()
        if temp:
            parts.append(temp)

        parts.append(self._section_trainers())
        parts.append(self._section_payment())
        parts.append(self._section_extras())
        parts.append(self._section_discounts())
        parts.append(self._section_hooks())

        return "\n\n".join(p for p in parts if p.strip())

    # ── приватные секции ─────────────────────────────────────────────────────

    def _section_memberships(self) -> str:
        lines = ["▌ АБОНЕМЕНТЫ — ЦЕНЫ И ЧТО ВХОДИТ"]
        for m in self.raw.get("memberships", []):
            base = m.get("base_price", 0)
            price_line = self._price_line(m)
            per_day = round(base / 365)
            monthly = round(base / 12)
            inc = " / ".join(m.get("includes", []))
            sauna = "сауна есть" if m.get("sauna_access") else "сауны нет"
            groups = (
                "групповые классы — ДА (BIG+, нужна запись)"
                if m.get("group_classes_access")
                else "групповых нет"
            )
            inbody = (
                "InBody чекап тела ВКЛЮЧЁН (% жира / воды / мышц — видишь прогресс в цифрах)"
                if any("InBody" in x for x in m.get("includes", []))
                else ""
            )
            lines.append(
                f"\n{m['name']} (id: {m.get('id','')})\n"
                f"  Цена: {price_line}\n"
                f"  В день: ~{per_day} тг | Рассрочка 0-0-12: ~{monthly} тг/мес\n"
                f"  Доступ: {m.get('access','')}\n"
                f"  Включает: {inc}\n"
                f"  {sauna} | {groups}"
                + (f"\n  {inbody}" if inbody else "")
            )
        return "\n".join(lines)

    def _section_bundles(self) -> str:
        bundles = self.raw.get("bundle_memberships") or []
        if not bundles:
            return ""
        lines = ["▌ ПАКЕТНЫЕ АБОНЕМЕНТЫ"]
        for b in bundles:
            base = b.get("base_price", 0)
            price_line = self._price_line(b)
            monthly = round(base / 12)
            inc = " / ".join(b.get("includes", []))
            tip = b.get("sell_tip", "").strip()
            lines.append(
                f"\n{b['name']} (id: {b.get('id','')})\n"
                f"  Цена: {price_line} | Рассрочка 0-0-12: ~{monthly} тг/мес\n"
                f"  Включает: {inc}\n"
                f"  Как продавать: {tip}"
            )
        return "\n".join(lines)

    def _section_temporary(self) -> str:
        items = self.raw.get("temporary_memberships", [])
        if not items:
            return ""
        lines = ["▌ ВРЕМЕННЫЕ ОФФЕРЫ (ограниченный срок)"]
        today = date.today()
        for t in items:
            start_s = t.get("start_date")
            end_s = t.get("end_date")
            try:
                start_d = date.fromisoformat(str(start_s)) if start_s else None
                end_d = date.fromisoformat(str(end_s)) if end_s else None
            except ValueError:
                start_d, end_d = None, None
            is_active = (start_d is None or start_d <= today) and (end_d is None or today <= end_d)
            status = "✅ АКТУАЛЬНО ПРЯМО СЕЙЧАС" if is_active else "⏸ вне периода действия"
            base = t.get("base_price", 0)
            monthly = round(base / 12) if base else 0
            inc = " / ".join(t.get("includes", []))
            lines.append(
                f"\n{t.get('name','Оффер')} (id: {t.get('id','')})\n"
                f"  Статус: {status}\n"
                f"  Цена: {self._price_line(t)}"
                + (f" | Рассрочка: ~{monthly} тг/мес" if monthly else "")
                + f"\n  Период: {start_s or '?'} — {end_s or '?'}\n"
                f"  Включает: {inc}\n"
                f"  {t.get('label','')}"
            )
        return "\n".join(lines)

    def _section_trainers(self) -> str:
        trainers = self.raw.get("trainers", {})
        lines = ["▌ ТРЕНЕРЫ"]
        if duty := trainers.get("duty"):
            lines.append(
                f"Дежурный тренер — включён во ВСЕ абонементы.\n"
                f"  {str(duty.get('description','')).strip()}\n"
                f"  Совет по продаже: {duty.get('sell_tip','')}"
            )
        if personal := trainers.get("personal"):
            lines.append(
                f"Персональный тренер — только в оффере 11+1 (первый месяц).\n"
                f"  {str(personal.get('description','')).strip()}\n"
                f"  Прайс у каждого тренера индивидуальный."
            )
        return "\n".join(lines)

    def _section_payment(self) -> str:
        payment = self.raw.get("payment", {})
        lines = ["▌ ОПЛАТА И РАССРОЧКА"]
        if inst := payment.get("installment"):
            lines.append(
                f"Рассрочка {inst.get('terms','')} через {inst.get('partners','')}.\n"
                f"  {inst.get('note','')}"
            )
        if two := payment.get("two_installments"):
            lines.append(
                f"Оплата в 2 транша: {two.get('description','')}\n"
                f"  ВНИМАНИЕ: {two.get('warning','')}"
            )
        return "\n".join(lines)

    def _section_extras(self) -> str:
        lines = ["▌ ДОПОЛНИТЕЛЬНО"]
        if freeze := self.raw.get("freeze"):
            lines.append(f"Заморозка до {freeze.get('max_days', 30)} дней — абонемент не сгорает при болезни или отъезде.")
        sauna_locs = [
            loc["address"]
            for loc in self.raw.get("locations", [])
            if loc.get("sauna")
        ]
        if sauna_locs:
            lines.append(f"Сауна есть на: {', '.join(sauna_locs)}.")
        group_locs = [
            f"{loc['address']} ({', '.join(loc.get('notes','').split('.') or [])})"
            for loc in self.raw.get("locations", [])
            if loc.get("hall_type") == "big_plus"
        ]
        if group_locs:
            lines.append(f"Групповые классы (йога, стретчинг, фитнес-микс) только на BIG+ залах: {', '.join(group_locs)}.")
        return "\n".join(lines)

    def _section_discounts(self) -> str:
        dd = self.daily_discounts
        today = date.today()
        if dd.valid_on == today and dd.discounts:
            lines = [f"▌ СКИДКИ СЕГОДНЯ {today.isoformat()} — ИСПОЛЬЗУЙ АКТИВНО, это мощный триггер:"]
            for d in dd.discounts:
                price_fmt = f"{d.discounted_price:,}".replace(",", " ")
                lines.append(f"  {d.label}: {price_fmt} тг")
            return "\n".join(lines)
        return "▌ СКИДОК НА СЕГОДНЯ НЕТ — работай с базовыми ценами, рассрочкой и хуками."

    def _section_hooks(self) -> str:
        today = date.today()
        lines = ["▌ ХУКИ — ВПЛЕТАЙ В ДИАЛОГ, НЕ ЖДИ ОСОБОГО МОМЕНТА"]

        # Active temporary offers go first — highest priority sales trigger
        active_temps = []
        for t in self.raw.get("temporary_memberships", []):
            try:
                start_d = date.fromisoformat(str(t["start_date"])) if t.get("start_date") else None
                end_d = date.fromisoformat(str(t["end_date"])) if t.get("end_date") else None
            except ValueError:
                start_d, end_d = None, None
            if (start_d is None or start_d <= today) and (end_d is None or today <= end_d):
                active_temps.append(t)

        if active_temps:
            lines.append("  🔴 АКТИВНЫЕ ОФФЕРЫ — ПРОДАВАЙ ПРИ ПЕРВОМ РАЗГОВОРЕ О ЦЕНЕ И ПРИ 'ДОРОГО':")
            for t in active_temps:
                base = t.get("base_price", 0)
                monthly = round(base / 12) if base else 0
                end_s = t.get("end_date", "?")
                lines.append(
                    f"  — {t.get('name','Оффер')}: {base:,} тг (рассрочка ~{monthly} тг/мес), "
                    f"действует до {end_s}. {t.get('label','')}"
                )

        hooks = self.raw.get("hooks", [])
        if hooks:
            lines.append("  Остальные хуки (вплетай по ситуации):")
            for h in hooks:
                lines.append(f"  — {h}")

        return "\n".join(lines)

    # ── утилита ──────────────────────────────────────────────────────────────

    def _price_line(self, m: dict) -> str:
        mid = m.get("id")
        base = m.get("base_price")
        today = date.today()
        if mid and base and self.daily_discounts.valid_on == today and self.daily_discounts.discounts:
            for d in self.daily_discounts.discounts:
                if d.membership_id == mid:
                    base_fmt = f"{base:,}".replace(",", " ")
                    disc_fmt = f"{d.discounted_price:,}".replace(",", " ")
                    return f"{base_fmt} → {disc_fmt} тг (АКЦИЯ ДНЯ)"
        return f"{base:,} тг".replace(",", " ") if base else "цена по запросу"


# ─── Загрузчик ──────────────────────────────────────────────────────────────

class ClubContextLoader:
    def __init__(self, path: str = "club_data/club_info.yaml"):
        self._path = Path(path)

    async def load(self) -> ClubContext:
        try:
            raw = self._load_yaml()
        except Exception:
            log.exception("Failed to load club_info.yaml")
            return ClubContext(gym_name="Underground Gym Astana", raw={})

        gym_name = raw.get("gym", {}).get("name", "Underground Gym Astana")
        dd_raw = raw.get("daily_discounts") or {}
        try:
            daily = DailyDiscounts.model_validate(
                {"date": dd_raw.get("date"), "discounts": dd_raw.get("discounts") or []}
            )
        except Exception:
            log.warning("Failed to parse daily_discounts")
            daily = DailyDiscounts()

        return ClubContext(gym_name=gym_name, raw=raw, daily_discounts=daily)

    def _load_yaml(self) -> dict:
        with open(self._path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
