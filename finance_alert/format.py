from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from finance_alert.models import Alert

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


def format_alerts(alerts: list[Alert], now: datetime | None = None) -> str:
    when = (now or datetime.now(timezone.utc)).astimezone(TZ)
    lines = [
        f"{BRAND} — swing 2–3% / ~7 giorni",
        f"{when.strftime('%Y-%m-%d %H:%M')} Roma",
        "",
        "Piano indicativo (non consiglio finanziario).",
        "",
    ]
    for tipo in TIPO_ORDER:
        gruppo = [a for a in alerts if a.tipo == tipo]
        if not gruppo:
            continue
        lines.append(TITOLO_GRUPPO.get(tipo, tipo))
        for alert in gruppo:
            score_bit = f" · {alert.setup_score}/10" if alert.setup_score else ""
            verdict_bit = f" · {alert.verdict}" if alert.verdict else ""
            lines.append(f"{alert.titolo}{score_bit}{verdict_bit}")
            lines.append(alert.body)
            if alert.url:
                lines.append(alert.url)
            lines.append("")
    text = "\n".join(lines).strip()
    return text[:3900]


def format_test_ping(status: dict[str, bool], n_watch: int) -> str:
    when = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    ready = [k for k, v in status.items() if v]
    missing = [k for k, v in status.items() if not v]
    lines = [
        f"🧪 PROVA — {BRAND}",
        f"{when} Roma",
        "",
        "Modalità swing trading (~7 giorni, target +2–3%):",
        "• surprise utili + piano ingresso/target/stop",
        "• gap pre/after-hours (solo se non già inseguito)",
        "• peer in ritardo nel settore",
        "• 8-K e news wire ad alto impatto",
        "",
        "Non garantisce profitto. Filtra setup sotto 6/10.",
        f"Watchlist: {n_watch} ticker",
        f"Fonti ok: {', '.join(ready) or 'nessuna'}",
    ]
    if missing:
        lines.append(f"Fonti senza chiave: {', '.join(missing)}")
    return "\n".join(lines)
