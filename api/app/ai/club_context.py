"""
club_context.py — данные клуба для промпта (сжатый текст, минимум токенов).
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)


class DailyDiscount(BaseModel):
    membership_id: str
    discounted_price: int
    label: str


class DailyDiscounts(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    valid_on: date | None = Field(default=None, alias="date")
    discounts: list[DailyDiscount] = Field(default_factory=list)


def _trunc(s: str, n: int) -> str:
    s = str(s).replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _inc_short(items: list | None, max_items: int = 2, max_chars: int = 100) -> str:
    if not items:
        return "—"
    parts = [_trunc(x, 55) for x in items[:max_items]]
    out = "; ".join(parts)
    return _trunc(out, max_chars)


class ClubContext(BaseModel):
    gym_name: str
    raw: dict
    daily_discounts: DailyDiscounts = DailyDiscounts()

    def to_prompt_text(self) -> str:
        parts = [
            self._hdr(),
            self._cards(),
            self._bundles(),
            self._temporary(),
            self._trainers_pay_misc(),
            self._discounts(),
            self._hooks_yaml(),
        ]
        return "\n".join(p for p in parts if p.strip())

    def _hdr(self) -> str:
        n = len(self.raw.get("locations") or [])
        return (
            f"▌КЛУБ {self.gym_name}\n"
            f"Точек: {n}. Один абонемент на сеть. Типы залов: GYM / BIG / BIG+ "
            f"(групповые только BIG+, запись). Бассейна нет."
        )

    def _cards(self) -> str:
        lines = ["▌КАРТЫ id·название·база·доступ·сауна·группы·InBody"]
        for m in self.raw.get("memberships", []):
            mid = m.get("id", "")
            nm = _trunc(m.get("name", ""), 22)
            pl = self._price_line(m)
            acc = _trunc(m.get("access", ""), 48)
            sn = "да" if m.get("sauna_access") else "нет"
            gr = "да" if m.get("group_classes_access") else "нет"
            ib = "да" if any("InBody" in str(x) for x in (m.get("includes") or [])) else "нет"
            lines.append(f"{mid}·{nm}·{pl}·{_trunc(acc, 44)}·сауна:{sn}·группы:{gr}·InBody:{ib}")
        return "\n".join(lines)

    def _bundles(self) -> str:
        bundles = self.raw.get("bundle_memberships") or []
        if not bundles:
            return ""
        lines = ["▌ПАКЕТЫ id·название·цена·вкратце"]
        for b in bundles:
            inc = _inc_short(b.get("includes"), 2, 90)
            lines.append(f"{b.get('id','')}·{_trunc(b.get('name',''), 16)}·{self._price_line(b)}·{inc}")
        return "\n".join(lines)

    def _temporary(self) -> str:
        items = self.raw.get("temporary_memberships") or []
        if not items:
            return ""
        lines = ["▌ВРЕМЕННЫЕ id·название·цена·период·статус·лейбл"]
        today = date.today()
        for t in items:
            start_s, end_s = t.get("start_date"), t.get("end_date")
            try:
                sd = date.fromisoformat(str(start_s)) if start_s else None
                ed = date.fromisoformat(str(end_s)) if end_s else None
            except ValueError:
                sd, ed = None, None
            ok = (sd is None or sd <= today) and (ed is None or today <= ed)
            st = "АКТ" if ok else "вне"
            lines.append(
                f"{t.get('id','')}·{_trunc(t.get('name',''), 14)}·{self._price_line(t)}·"
                f"{start_s}—{end_s}·{st}·{_trunc(t.get('label') or '', 50)}"
            )
        return "\n".join(lines)

    def _trainers_pay_misc(self) -> str:
        lines: list[str] = ["▌ТРЕНЕРЫ И ОПЛАТА"]
        tr = self.raw.get("trainers") or {}
        if tr.get("duty"):
            lines.append("Дежурный: во все карты, в зале, не персонал.")
        if tr.get("personal"):
            lines.append("Персональный: только оффер 11+1 (1-й мес), дальше свой прайс.")
        pay = self.raw.get("payment") or {}
        if inst := pay.get("installment"):
            lines.append(f"Рассрочка: {inst.get('terms','')} {inst.get('partners','')}")
        if two := pay.get("two_installments"):
            lines.append(f"2 транша: {_trunc(str(two.get('description','')), 70)}")
        if fr := self.raw.get("freeze"):
            lines.append(f"Заморозка до {fr.get('max_days', 30)} дн.")
        sauna_addrs = []
        for loc in self.raw.get("locations", []) or []:
            if loc.get("sauna"):
                sauna_addrs.append(_trunc(str(loc.get("address", "")), 22))
        if sauna_addrs:
            lines.append("Сауна (есть не везде): " + ", ".join(sauna_addrs[:5]))
        lines.append("Групповые классы: только BIG+, запись.")
        return "\n".join(lines)

    def _discounts(self) -> str:
        dd = self.daily_discounts
        today = date.today()
        if dd.valid_on == today and dd.discounts:
            parts = [f"▌СКИДКИ {today.isoformat()}"]
            for d in dd.discounts:
                pf = f"{d.discounted_price:,}".replace(",", " ")
                parts.append(f"{d.membership_id}: {pf} тг — {_trunc(d.label, 60)}")
            return "\n".join(parts)
        return "▌СКИДКИ: на сегодня нет (дата в конфиге не сегодня или список пуст)."

    def _hooks_yaml(self) -> str:
        hooks = self.raw.get("hooks") or []
        if not hooks:
            return ""
        lines = ["▌ХУКИ (из конфига, вплетай по ситуации)"]
        for h in hooks:
            lines.append(f"— {_trunc(h, 95)}")
        return "\n".join(lines)

    def _price_line(self, m: dict) -> str:
        mid = m.get("id")
        base = m.get("base_price")
        today = date.today()
        if mid and base and self.daily_discounts.valid_on == today and self.daily_discounts.discounts:
            for d in self.daily_discounts.discounts:
                if d.membership_id == mid:
                    bf = f"{base:,}".replace(",", " ")
                    df = f"{d.discounted_price:,}".replace(",", " ")
                    return f"{bf}→{df}"
        return f"{base:,}".replace(",", " ") if base else "?"


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
