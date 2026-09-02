from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from finance_alert.models import Alert
from finance_alert.unified_config import load_unified_config

try:
    from finance_alert.enrich import build_context_block, enrich_alert
except ImportError:  # pragma: no cover
    enrich_alert = None  # type: ignore
    build_context_block = None  # type: ignore

TZ = ZoneInfo("Europe/Rome")
BRAND = "FINANCE NOTIFY"

TIPO_ORDER = [
    "earnings_surprise",
    "filing_8k",
    "extended_hours",
    "peer_lag",
    "news",
    "earnings_soon",
    "price_spike",
    "momentum",
    "digest_earnings",
]

TITOLO_GRUPPO = {
    "earnings_surprise": "Utili — sorpresa positiva",
    "extended_hours": "Gap pre / after-hours",
    "price_spike": "Movimento in seduta",
    "peer_lag": "Peer in ritardo (catch-up)",
    "momentum": "Momentum breve",
    "filing_8k": "Filing SEC 8-K",
    "news": "Catalizzatore wire",
    "earnings_soon": "Watchlist utili",
    "digest_earnings": "Digest utili",
}


def _tv_symbol(ticker: str) -> str:
    return ticker.upper()


def _quick_links(alert: Alert) -> list[str]:
    sym = _tv_symbol(alert.ticker)
    if sym == "*":
        return []
    lines = [f"Chart: https://www.tradingview.com/chart/?symbol={sym}"]
    if alert.url:
        label = "SEC filing" if alert.tipo == "filing_8k" else "Fonte"
        lines.append(f"{label}: {alert.url}")
    return lines


def format_alerts(
    alerts: list[Alert],
    now: datetime | None = None,
    *,
    macro_stress: bool = False,
    with_unified: bool | None = None,
) -> str:
    when = (now or datetime.now(timezone.utc)).astimezone(TZ)
    unified_on = with_unified
    if unified_on is None:
        unified_on = load_unified_config().rules.enrich_telegram
    lines = [
        f"{BRAND} — swing 2–3% / ~7 giorni",
        f"{when.strftime('%Y-%m-%d %H:%M')} Roma",
        "",
        "Piano indicativo (non consiglio finanziario).",
    ]
    if unified_on:
        lines.append("📊 Quant Platform: score fondamentale + quant + regolatori.")
    if macro_stress:
        lines.append("Mercato debole (SPY/QQQ): soglia setup alzata a 8/10.")
    lines.append("")
    for tipo in TIPO_ORDER:
        gruppo = [a for a in alerts if a.tipo == tipo]
        if not gruppo:
            continue
        lines.append(TITOLO_GRUPPO.get(tipo, tipo))
        for alert in gruppo:
            tag_bits = [t for t in alert.tags if t]
            if tag_bits:
                tag_bits = [f"[{t}]" for t in tag_bits]
            score_bit = f" · {alert.setup_score}/10" if alert.setup_score else ""
            verdict_bit = f" · {alert.verdict}" if alert.verdict else ""
            tag_bit = f" {' '.join(tag_bits)}" if tag_bits else ""
            lines.append(f"{alert.titolo}{score_bit}{verdict_bit}{tag_bit}")
            lines.append(alert.body)
            if unified_on and enrich_alert and build_context_block and alert.ticker not in ("*", ""):
                try:
                    ctx = enrich_alert(alert)
                    if ctx:
                        lines.append("")
                        lines.extend(build_context_block(ctx).splitlines())
                except Exception:
                    pass
            lines.extend(_quick_links(alert))
            lines.append("")
    text = "\n".join(lines).strip()
    return text[:3900]


def format_test_ping(status: dict[str, bool], n_watch: int) -> str:
    when = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    ready = [k for k, v in status.items() if v]
    missing = [k for k, v in status.items() if v is False]
    lines = [
        f"🧪 PROVA — {BRAND}",
        f"{when} Roma",
        "",
        "Modalità swing trading (~7 giorni, target +2–3%):",
        "• surprise utili + piano ingresso/target/stop",
        "• gap pre/after-hours (RVOL + liquidità $)",
        "• peer in ritardo + resistenza tecnica",
        "• 8-K e news wire (LLM se configurato)",
        "",
        "RVOL da cache giornaliera · macro SPY/QQQ · link TradingView.",
        f"Watchlist: {n_watch} ticker",
        f"Fonti ok: {', '.join(ready) or 'nessuna'}",
    ]
    if missing:
        lines.append(f"Fonti senza chiave: {', '.join(missing)}")
    return "\n".join(lines)
