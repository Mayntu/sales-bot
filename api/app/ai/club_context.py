"""
club_context.py — данные клуба для промпта (сжатый текст, минимум токенов).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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


@dataclass(frozen=True)
class FollowupAnchorCard:
    membership_id: str
    display_name: str
    price_tg: int
    monthly_tg: int
    per_day_tg: int


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

    def _temporary_membership_active_today(self, t: dict) -> bool:
        today = date.today()
        start_s, end_s = t.get("start_date"), t.get("end_date")
        try:
            sd = date.fromisoformat(str(start_s)) if start_s else None
            ed = date.fromisoformat(str(end_s)) if end_s else None
        except ValueError:
            return False
        return (sd is None or sd <= today) and (ed is None or today <= ed)

    def followup_anchor_card(self) -> FollowupAnchorCard | None:
        today = date.today()

        def _eff_price(mid: str, base: int) -> int:
            if self.daily_discounts.valid_on == today and self.daily_discounts.discounts:
                for d in self.daily_discounts.discounts:
                    if d.membership_id == mid:
                        return int(d.discounted_price)
            return base

        gold: dict | None = None
        for m in self.raw.get("memberships") or []:
            if m.get("id") == "gold":
                gold = m
                break
        if gold is None:
            memberships = list(self.raw.get("memberships") or [])
            gold = memberships[0] if memberships else None
        if not gold or not gold.get("base_price"):
            return None
        mid = str(gold.get("id", "gold"))
        base_raw = int(gold["base_price"])
        price = _eff_price(mid, base_raw)
        nm = str(gold.get("name", "Золотая"))
        monthly = price // 12
        per_day = max(1, round(price / 365))
        return FollowupAnchorCard(
            membership_id=mid,
            display_name=nm,
            price_tg=price,
            monthly_tg=monthly,
            per_day_tg=per_day,
        )

    def has_promo_for_followup_3d(self) -> bool:
        today = date.today()
        dd = self.daily_discounts
        if dd.valid_on == today and dd.discounts:
            return True
        for t in self.raw.get("temporary_memberships") or []:
            if self._temporary_membership_active_today(t):
                return True
        return False

    def followup_promo_one_liner(self) -> str | None:
        today = date.today()
        dd = self.daily_discounts
        if dd.valid_on == today and dd.discounts:
            d = dd.discounts[0]
            pf = f"{d.discounted_price:,}".replace(",", " ")
            return f"{_trunc(d.label, 44)} — {pf} тг"
        for t in self.raw.get("temporary_memberships") or []:
            if not self._temporary_membership_active_today(t):
                continue
            nm = _trunc(str(t.get("name") or t.get("id", "")), 40)
            pl = self._price_line(t)
            return f"{nm} ({pl} тг)"
        return None

    def followup_facts_for_prompt(self) -> str:
        """
        Короткий набор фактов для follow-up сообщений (без простыни по всем картам).
        """
        lines: list[str] = [f"Клуб: {self.gym_name}"]

        def _effective_base(membership_id: str, base_price: int) -> int:
            today = date.today()
            dd = self.daily_discounts
            if dd.valid_on == today and dd.discounts:
                for d in dd.discounts:
                    if d.membership_id == membership_id:
                        return int(d.discounted_price)
            return base_price

        gold: dict | None = None
        for m in self.raw.get("memberships") or []:
            if m.get("id") == "gold":
                gold = m
                break
        if gold is None:
            memberships = list(self.raw.get("memberships") or [])
            gold = memberships[0] if memberships else None

        if gold and gold.get("base_price"):
            mid = gold.get("id", "gold")
            base_raw = int(gold["base_price"])
            price = _effective_base(str(mid), base_raw)
            nm = gold.get("name", "Золотая")
            monthly = price // 12
            per_day = max(1, round(price / 365))
            lines.append(f"Образец «якорной» карты ({nm}, id={mid}): сумма ~{price:,} тг".replace(",", " "))
            lines.append(f"  → из неё считай: ~{monthly:,} тг в месяц при /12 рассрочке, ~{per_day:,} тг в день (365)".replace(",", " "))

        today = date.today()
        dd = self.daily_discounts
        if dd.valid_on == today and dd.discounts:
            lines.append(f"Скидки на {today.isoformat()}:")
            for d in dd.discounts[:3]:
                pf = f"{d.discounted_price:,}".replace(",", " ")
                lines.append(f"  • {d.membership_id}: {pf} тг — {_trunc(d.label, 70)}")
        else:
            lines.append(f"Отдельных «скидок дня» на {today.isoformat()} в конфиге нет.")

        temps = []
        for t in self.raw.get("temporary_memberships") or []:
            start_s, end_s = t.get("start_date"), t.get("end_date")
            try:
                sd = date.fromisoformat(str(start_s)) if start_s else None
                ed = date.fromisoformat(str(end_s)) if end_s else None
            except ValueError:
                sd, ed = None, None
            if (sd is None or sd <= today) and (ed is None or today <= ed):
                lbl = _trunc(str(t.get("label") or t.get("name", "")), 60)
                pl = self._price_line(t)
                temps.append(f"{t.get('name', '')} ({pl} тг) — {lbl}")
        lines.append(
            "Активные временные офферы: " + ("; ".join(temps[:2]) if temps else "нет в периоде «сегодня».")
        )

        hooks = self.raw.get("hooks") or []
        trial = False
        for h in hooks:
            if "5000" in str(h):
                trial = True
                break
        lines.append(
            "Пробная первой тренировки платная около 5000 тг — как в хуках конфига."
            if trial
            else "Пробный визит/цена пробной — смотри блок ДАННЫЕ КЛУБА ниже если нужно (не более одной строки в ответе)."
        )

        pay = self.raw.get("payment") or {}
        if inst := pay.get("installment"):
            lines.append(f"Рассрочка: {inst.get('terms','')} через {inst.get('partners','')}")

        return "\n".join(lines)

    def _price_line(self, m: dict) -> str:
        mid = m.get("id")
        base = m.get("base_price")
        monthly_tag = "·мес" if str(m.get("price_period") or "").lower() == "monthly" else ""
        today = date.today()
        if mid and base and self.daily_discounts.valid_on == today and self.daily_discounts.discounts:
            for d in self.daily_discounts.discounts:
                if d.membership_id == mid:
                    bf = f"{base:,}".replace(",", " ")
                    df = f"{d.discounted_price:,}".replace(",", " ")
                    return f"{bf}→{df}{monthly_tag}"
        return (f"{base:,}".replace(",", " ") if base else "?") + monthly_tag


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
