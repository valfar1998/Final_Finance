#!/usr/bin/env python3
"""
Smart money / 13F via Dataroma (superinvestor holdings).

Usato solo come BONUS di conferma (+0…+3), mai come motivo principale di acquisto.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DATAROMA_STOCK = "https://www.dataroma.com/m/stock.php?sym={sym}"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

# Tier 1: buy-and-hold / qualità (max +3)
TIER1 = {
    "warren buffett",
    "berkshire hathaway",
    "charlie munger",
    "mohnish pabrai",
    "pabrai",
    "li lu",
    "himalaya capital",
    "duan yongping",
    "terry smith",
    "fundsmith",
    "nick sleep",
    "zakaria",
    "chris hohn",  # TCI — lungo termine qualità
    "tci fund",
}

# Tier 2: macro / value attivo (max +2)
TIER2 = {
    "druckenmiller",
    "duquesne",
    "george soros",
    "soros fund",
    "stanley druckenmiller",
    "david tepper",
    "appaloosa",
    "seth klarman",
    "baupost",
    "howard marks",
    "oaktree",
    "bill nygren",
    "oakmark",
    "thomas gayner",
    "markel",
    "francois rochon",
    "giverny",
    "bruce berkowitz",
    "fairholme",
}

# Tier 3: attivisti / catalyst (max +1)
TIER3 = {
    "carl icahn",
    "icahn",
    "daniel loeb",
    "third point",
    "bill ackman",
    "pershing square",
    "nelson peltz",
    "trian",
    "elliott",
    "paul singer",
}

# Esclusi esplicitamente dal bonus positivo (rumore / stile non replicabile)
IGNORE_POSITIVE = {
    "cathie wood",
    "ark invest",
    "arkk",
    "michael burry",
    "scion",
    "tiger global",
    "softbank",
}


@dataclass
class SuperHolder:
    name: str
    portfolio_pct: float | None
    activity: str  # Buy, Add, Reduce, Sell, Hold/empty
    shares: float | None = None
    value: float | None = None
    tier: int = 0  # 1,2,3 or 0


@dataclass
class SmartMoneyResult:
    ok: bool
    ticker: str
    holders: list[SuperHolder] = field(default_factory=list)
    bonus: float = 0.0
    max_bonus: float = 3.0
    notes: list[str] = field(default_factory=list)
    source_url: str = ""
    error: str | None = None


def _base_symbol(ticker: str) -> str:
    """Dataroma usa ticker US senza exchange; internazionali spesso non ci sono."""
    t = (ticker or "").strip().upper()
    if "." in t:
        # 285A.T, BREN.JK, 000660.KS → raramente su Dataroma
        base, suf = t.rsplit(".", 1)
        if suf in {"KS", "KQ", "T", "JK", "HK", "SS", "SZ", "TW", "AX", "SI"}:
            return base  # tenteremo comunque
        # BRK-B style already without dot; SAP.DE → SAP
        return base
    return t.replace("-", ".") if False else t


def _tier_for(name: str) -> int:
    low = name.lower()
    for bad in IGNORE_POSITIVE:
        if bad in low:
            return -1
    for key in TIER1:
        if key in low:
            return 1
    for key in TIER2:
        if key in low:
            return 2
    for key in TIER3:
        if key in low:
            return 3
    return 0


def _parse_pct(raw: str) -> float | None:
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw.replace(",", ""))
    return float(m.group(1)) if m else None


def _parse_activity(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw.strip())
    if not s:
        return "Hold"
    low = s.lower()
    # conserva "Reduce 46.05%" / "Add 1.65%" / "Buy"
    if low.startswith("buy"):
        return s if len(s) < 40 else "Buy"
    if low.startswith("add"):
        return s if len(s) < 40 else s[:40]
    if low.startswith("reduce"):
        return s if len(s) < 40 else s[:40]
    if low.startswith("sell"):
        return s if len(s) < 40 else "Sell"
    return s[:40]


def _activity_kind(activity: str) -> str:
    low = (activity or "").lower()
    if low.startswith("buy"):
        return "Buy"
    if low.startswith("add"):
        return "Add"
    if low.startswith("reduce"):
        return "Reduce"
    if low.startswith("sell"):
        return "Sell"
    return "Hold"


def _activity_change_pct(activity: str) -> float | None:
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", activity or "")
    return float(m.group(1)) if m else None


def fetch_dataroma_holders(ticker: str, timeout: int = 18) -> SmartMoneyResult:
    sym = _base_symbol(ticker)
    url = DATAROMA_STOCK.format(sym=sym)
    out = SmartMoneyResult(ok=False, ticker=sym, source_url=url)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        out.error = f"Dataroma non raggiungibile: {exc}"
        out.notes.append(out.error)
        return out

    if "No matching stock found" in html or "not found" in html.lower()[:500]:
        out.error = f"Nessun superinvestor Dataroma per {sym}"
        out.notes.append(out.error)
        out.ok = True  # fetch ok, zero holders
        return out

    # Righe tabella: nome manager + % portfolio + activity
    row_re = re.compile(
        r"holdings\.php\?m=[A-Z0-9]+[^>]*>([^<]+)</a>\s*</td>\s*"
        r"<td[^>]*>\s*([0-9.,]+)\s*</td>\s*"
        r"<td[^>]*>(.*?)</td>",
        re.I | re.S,
    )
    holders: list[SuperHolder] = []
    for m in row_re.finditer(html):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        pct = _parse_pct(m.group(2))
        act_raw = re.sub(r"<[^>]+>", " ", m.group(3))
        act_raw = re.sub(r"\s+", " ", act_raw).strip()
        activity = _parse_activity(act_raw)
        tier = _tier_for(name)
        holders.append(
            SuperHolder(
                name=name,
                portfolio_pct=pct,
                activity=activity,
                tier=tier,
            )
        )

    # Fallback più permissivo se regex stretta fallisce
    if not holders:
        for m in re.finditer(
            r"holdings\.php\?m=[A-Z0-9]+[^>]*>([^<]+)</a>",
            html,
            re.I,
        ):
            name = re.sub(r"\s+", " ", m.group(1)).strip()
            holders.append(
                SuperHolder(name=name, portfolio_pct=None, activity="Hold", tier=_tier_for(name))
            )

    out.holders = holders
    out.ok = True
    return out


def score_smart_money(
    ticker: str,
    *,
    base_score: float,
    reliable: bool,
    preliminary_verdict: str,
) -> SmartMoneyResult:
    """
    Calcola bonus 13F/Dataroma.

    Regole:
    - Solo se reliable e verdetto preliminare COMPRA*/NEUTRO
    - Mai bonus se EVITA / DATI INSUFFICIENTI
    - Solo posizioni significative (≥1% portafoglio; pieno credito ≥5%)
    - Cap +3; vendite massicce tier1/2 → fino a -2
    """
    result = fetch_dataroma_holders(ticker)
    if not result.ok and result.error:
        result.bonus = 0
        return result

    if not reliable or preliminary_verdict in {"EVITA", "EVITA FORTE", "DATI INSUFFICIENTI"}:
        result.bonus = 0
        result.notes.append(
            f"Bonus disattivato (verdetto {preliminary_verdict}) — smart money non sovrascrive EVITA/dati insufficienti"
        )
        # comunque elenca chi c'è
        _summarize_holders(result)
        return result

    if base_score < 40:
        result.bonus = 0
        result.notes.append("Bonus disattivato: score base < 40")
        _summarize_holders(result)
        return result

    best_pos = 0.0
    sell_penalty = 0.0
    seen: list[str] = []

    for h in result.holders:
        if h.tier <= 0:
            continue
        pct = h.portfolio_pct if h.portfolio_pct is not None else 0.0
        kind = _activity_kind(h.activity)
        chg = _activity_change_pct(h.activity)

        # soglia: ignora posizioni trascurabili (salvo buy/add nuovi)
        if pct < 1.0 and kind not in {"Buy", "Add"}:
            continue
        if pct < 0.5 and kind in {"Buy", "Add"}:
            continue

        weight = 1.0 if pct >= 5.0 else (0.6 if pct >= 1.0 else 0.35)

        if kind in {"Reduce", "Sell"}:
            if h.tier in (1, 2) and pct >= 1.0:
                if kind == "Sell" or (chg is not None and chg >= 25):
                    pen = -2.0 if pct >= 5.0 else -1.0
                elif chg is not None and chg >= 10:
                    pen = -1.0 if pct >= 5.0 else -0.5
                else:
                    pen = -0.5 if pct >= 5.0 else -0.25
                sell_penalty = min(sell_penalty, pen)
                seen.append(f"⚠ {h.name}: {h.activity} ({pct:.1f}% port.)")
            continue

        if h.tier == 1:
            pts = 3.0 * weight
        elif h.tier == 2:
            pts = 2.0 * weight
        else:
            pts = 1.0 * weight

        if pts > best_pos:
            best_pos = pts
            tag = {1: "T1 buy&hold", 2: "T2 macro/value", 3: "T3 activist"}[h.tier]
            seen.insert(
                0,
                f"✓ {h.name} [{tag}] {pct:.1f}% port. · {h.activity}",
            )

    bonus = best_pos + sell_penalty
    bonus = max(-2.0, min(3.0, bonus))
    result.bonus = round(bonus, 2)
    if seen:
        result.notes.extend(seen[:6])
    else:
        result.notes.append("Nessun superinvestor tracciato (o posizioni <1%)")
    if result.bonus > 0:
        result.notes.append(f"Bonus conferma +{result.bonus:.0f} (cap 3) — non è segnale standalone")
    elif result.bonus < 0:
        result.notes.append(f"Malus vendite smart money {result.bonus:.0f}")
    return result


def _summarize_holders(result: SmartMoneyResult) -> None:
    notable = [h for h in result.holders if h.tier > 0][:5]
    if not notable:
        # mostra comunque top per info
        for h in result.holders[:3]:
            pct = f"{h.portfolio_pct:.1f}%" if h.portfolio_pct is not None else "?"
            result.notes.append(f"· {h.name} ({pct} port., {h.activity})")
        if not result.holders:
            result.notes.append("Nessun holder Dataroma")
        return
    for h in notable:
        pct = f"{h.portfolio_pct:.1f}%" if h.portfolio_pct is not None else "?"
        result.notes.append(f"· T{h.tier} {h.name} ({pct}, {h.activity})")


def smart_money_to_dict(result: SmartMoneyResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "ticker": result.ticker,
        "bonus": result.bonus,
        "notes": result.notes,
        "source_url": result.source_url,
        "error": result.error,
        "holders": [
            {
                "name": h.name,
                "portfolio_pct": h.portfolio_pct,
                "activity": h.activity,
                "tier": h.tier,
            }
            for h in result.holders[:20]
        ],
    }
