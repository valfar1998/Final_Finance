from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from finance_alert.models import Alert

TZ = ZoneInfo("Europe/Rome")

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
    "earnings_surprise": "Utili — surprise (catalizzatore)",
    "extended_hours": "Gap precoce pre/after hours",
    "price_spike": "Movimento già avvenuto",
    "peer_lag": "Peer ancora fermi (catch-up?)",
    "momentum": "Momentum breve",
    "filing_8k": "Filing SEC (8-K)",
    "news": "Catalizzatore news",
    "earnings_soon": "Setup utili in arrivo",
    "digest_earnings": "Digest utili",
}


def format_alerts(alerts: list[Alert], now: datetime | None = None) -> str:
    when = (now or datetime.now(timezone.utc)).astimezone(TZ)
    lines = [f"Borsa — alert ({when.strftime('%Y-%m-%d %H:%M')} Roma)", ""]
    for tipo in TIPO_ORDER:
        gruppo = [a for a in alerts if a.tipo == tipo]
        if not gruppo:
            continue
        lines.append(TITOLO_GRUPPO.get(tipo, tipo))
        for alert in gruppo:
            lines.append(alert.titolo)
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
        f"PROVA — Borsa alert ({when} Roma)",
        "",
        "Modalità ANTICIPO — avvisi principali:",
        "• utili in arrivo (setup)",
        "• surprise EPS / 8-K appena fuori",
        "• gap precoce pre/after-hours",
        "• peer del cluster ancora fermi",
        "• catalizzatore wire (guidance, M&A, FDA)",
        "",
        "Non predice il +X% prima della notizia; intercetta il setup.",
        f"Watchlist: {n_watch} ticker",
        f"Fonti ok: {', '.join(ready) or 'nessuna'}",
    ]
    if missing:
        lines.append(f"Fonti senza chiave: {', '.join(missing)}")
    return "\n".join(lines)
