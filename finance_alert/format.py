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

WHY_BY_TIPO = {
    "extended_hours": (
        "Il titolo si muove fuori dalla seduta regolare con volume sopra la media. "
        "È un possibile setup swing (orizzonte ~7 giorni, obiettivo indicativo +2–3%), "
        "non un ordine automatico di compra."
    ),
    "news": (
        "È uscita una notizia operativa (M&A, guidance, utili, ecc.) collegata al ticker. "
        "Lo score indica quanto il setup swing è interessante oggi; "
        "non garantisce che il prezzo salga."
    ),
    "earnings_surprise": (
        "Gli utili pubblicati battono (o mancano) le stime: spesso muovono il prezzo "
        "nei giorni successivi."
    ),
    "filing_8k": (
        "C’è un filing ufficiale SEC 8-K (evento societario rilevante). "
        "Il mercato può reagire nelle ore/giorni successivi."
    ),
    "peer_lag": (
        "Un peer del settore è già salito; questo ticker è ancora indietro "
        "e potrebbe recuperare (catch-up), non è certo."
    ),
    "price_spike": (
        "Movimento forte già in seduta: spesso è tardi per entrare; "
        "valuta solo se c’è ancora spazio verso target/stop."
    ),
    "momentum": (
        "Accelerazione di prezzo su barre brevi: segnale tempestivo ma fragile."
    ),
    "earnings_soon": (
        "Utili in arrivo: alta volatilità attesa. Solo watchlist, non ingresso."
    ),
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


def _pct(from_px: float | None, to_px: float | None) -> str:
    if from_px is None or to_px is None or from_px == 0:
        return ""
    return f" ({(to_px - from_px) / from_px * 100:+.1f}%)"


def _fact_lines(alert: Alert) -> list[str]:
    """Righe di fatto dall'body, senza il blocco Setup swing (lo riscriviamo sotto)."""
    out: list[str] = []
    for raw in (alert.body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("setup swing:"):
            break
        if low.startswith("ingresso ideale:") or low.startswith("target ") or low.startswith("stop:"):
            break
        if low.startswith("orizzonte ~") or low.startswith("movimento in corso"):
            break
        if low.startswith("già ") and "non inseguire" in low:
            break
        out.append(line)
    return out


def _why_lines(alert: Alert) -> list[str]:
    base = WHY_BY_TIPO.get(
        alert.tipo,
        "Segnale tecnico/fondamentale del motore alert. Valuta sempre rischio e size.",
    )
    lines = [base]
    if alert.verdict and "ATTENDI" in alert.verdict.upper():
        lines.append("Attenzione: il movimento è già esteso — meglio aspettare un rientro.")
    elif alert.verdict and "ingresso rapido" in alert.verdict.lower():
        lines.append("Il prezzo si sta già muovendo: entra solo se accetti poco slippage.")
    if any("LLM Unverified" == t for t in alert.tags):
        lines.append("Nota: catalizzatore non verificato da LLM (fallback keyword).")
    return lines


def _plan_lines(alert: Alert) -> list[str]:
    if alert.tipo == "earnings_soon" or (alert.verdict or "").upper().startswith("SOLO WATCHLIST"):
        return ["Nessun ingresso consigliato — solo da tenere d’occhio."]
    if (alert.verdict or "").upper().startswith("BLOCCATO"):
        return [f"Setup bloccato: {alert.verdict}"]

    lines: list[str] = []
    score = alert.setup_score
    verdict = alert.verdict or "n/d"
    if score:
        lines.append(f"Setup swing: {score}/10 · {verdict}")
    else:
        lines.append(f"Verdetto setup: {verdict}")

    entry = alert.entry_price
    target = alert.target_price
    stop = alert.stop_price

    # Fallback: recupera range dall'body se i campi non sono valorizzati
    body = alert.body or ""
    if entry is None:
        for line in body.splitlines():
            if line.lower().startswith("ingresso ideale:"):
                lines.append(line.strip())
                break
    else:
        # Se body ha un range, preferiscilo; altrimenti punto medio
        range_line = next(
            (ln.strip() for ln in body.splitlines() if ln.lower().startswith("ingresso ideale:")),
            "",
        )
        if range_line:
            lines.append(range_line)
        else:
            lines.append(f"Ingresso indicativo: ${entry:.2f}")

    if target is not None:
        lines.append(f"Target ~7g: ${target:.2f}{_pct(entry, target)} — obiettivo indicativo, non garantito")
    if stop is not None:
        lines.append(f"Stop: ${stop:.2f}{_pct(entry, stop)} — livello di uscita se sbagli")

    for line in body.splitlines():
        low = line.strip().lower()
        if low.startswith("orizzonte ~") or low.startswith("movimento in corso") or (
            low.startswith("già ") and "non inseguire" in low
        ):
            lines.append(line.strip())
            break

    lines.append("Non è un consiglio finanziario: size piccola e stop obbligatorio.")
    return lines


def _format_one_alert(alert: Alert, *, unified_on: bool) -> list[str]:
    gruppo = TITOLO_GRUPPO.get(alert.tipo, alert.tipo)
    head = f"▸ {alert.ticker} · {gruppo}"
    if alert.setup_score:
        head += f" · {alert.setup_score}/10"
    if alert.verdict:
        head += f" · {alert.verdict}"
    extra_tags = [t for t in alert.tags if t and t not in {"Trade Republic US", "LLM Unverified", "In crescita oggi"}]
    lines = [head]
    if "Trade Republic US" in alert.tags:
        lines.append("Universo Trade Republic US (se listato).")
    if extra_tags:
        lines.append("Tag: " + ", ".join(extra_tags))
    lines.append("")

    lines.append("1️⃣ Cosa è successo")
    facts = _fact_lines(alert)
    if facts:
        lines.extend(facts)
    else:
        lines.append(alert.titolo or "Evento rilevato dal motore alert.")
    lines.append("")

    lines.append("2️⃣ Perché è segnalato (e perché potrebbe interessare)")
    lines.extend(_why_lines(alert))
    lines.append("")

    lines.append("3️⃣ Cosa fare (piano swing ~7 giorni)")
    lines.extend(_plan_lines(alert))

    if unified_on and enrich_alert and build_context_block and alert.ticker not in ("*", ""):
        try:
            ctx = enrich_alert(alert)
            if ctx:
                lines.append("")
                lines.append("4️⃣ Contesto titolo (lungo periodo — NON è il segnale di oggi)")
                lines.extend(build_context_block(ctx).splitlines())
        except Exception:
            pass

    lines.extend(_quick_links(alert))
    lines.append("")
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
        f"{BRAND} — idea swing ~7 giorni (target indicativo +2–3%)",
        f"{when.strftime('%Y-%m-%d %H:%M')} Roma",
        "",
        "Legenda: 1) fatto  2) perché segnalato  3) piano ingresso/target/stop.",
        "Piano indicativo — non è un consiglio finanziario.",
    ]
    if unified_on:
        lines.append(
            "Il blocco «Contesto titolo» (COMPRA/EVITA) è valutazione di fondo, "
            "separata dal setup swing di oggi."
        )
    if macro_stress:
        lines.append("Mercato debole (SPY/QQQ): soglia setup alzata a 8/10.")
    lines.append("")
    for tipo in TIPO_ORDER:
        gruppo = [a for a in alerts if a.tipo == tipo]
        if not gruppo:
            continue
        for alert in gruppo:
            lines.extend(_format_one_alert(alert, unified_on=unified_on))
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
        "Ogni alert spiega: cosa è successo → perché segnalato → piano.",
        "RVOL da cache giornaliera · macro SPY/QQQ · link TradingView.",
        f"Watchlist: {n_watch} ticker",
        f"Fonti ok: {', '.join(ready) or 'nessuna'}",
    ]
    if missing:
        lines.append(f"Fonti senza chiave: {', '.join(missing)}")
    return "\n".join(lines)
