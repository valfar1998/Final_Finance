from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from finance_alert.config import AppConfig, Rules, SwingRules
from finance_alert.models import Alert, EarningsEvent, Filing, NewsItem, Quote
from finance_alert.news_llm import llm_available, verify_news_catalyst
from finance_alert.swing import build_swing_plan
from finance_alert.technical import compute_atr, fmt_resistance, nearest_resistance

HOUR_LABEL = {
    "bmo": "prima dell'apertura (BMO)",
    "amc": "dopo chiusura (AMC)",
    "dmh": "durante la seduta",
}


def _label(hour: str) -> str:
    return HOUR_LABEL.get((hour or "").lower(), hour or "orario n.d.")


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "n.d."
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"{value:.2f}"


def _fmt_eps(value: float | None) -> str:
    return "n.d." if value is None else f"${value:.2f}"


def _fmt_pct(value: float | None) -> str:
    return "n.d." if value is None else f"{value:+.1f}%"


def _name(cfg: AppConfig, ticker: str) -> str:
    item = cfg.by_symbol(ticker)
    return item.name if item else ticker


def _publisher_key(item: NewsItem) -> str:
    return (item.publisher or item.source or "").strip().lower()


def _high_beta_tickers(cfg: AppConfig) -> set[str]:
    out: set[str] = set()
    for cluster in cfg.clusters:
        if cluster.name.lower() == "high_beta":
            out.update(cluster.tickers)
    return out


def _passes_rvol(quote: Quote, rules: Rules, *, for_spike: bool = False) -> bool:
    vol_rules = rules.volume
    required = vol_rules.require_for_spike if for_spike else vol_rules.require_for_extended
    if not required:
        return True
    if quote.rvol is None:
        return False
    return quote.rvol >= vol_rules.min_rvol


def _passes_dollar_volume(
    quote: Quote,
    cfg: AppConfig,
    rules: Rules,
    *,
    for_peer: bool = False,
) -> bool:
    vol_rules = rules.volume
    required = vol_rules.require_dollar_volume_peer if for_peer else vol_rules.require_dollar_volume_extended
    if not required:
        return True
    if quote.dollar_volume is None:
        return False
    minimum = vol_rules.min_dollar_volume
    if quote.ticker.upper() in _high_beta_tickers(cfg):
        minimum = vol_rules.min_dollar_volume_high_beta
    return quote.dollar_volume >= minimum


def _gap_exceeds_atr_target(quote: Quote, swing: SwingRules) -> bool:
    """Scarta se il gap pre/post ha già assorbito l'upside ATR (rischio di comprare i massimi)."""
    session = (quote.session or "regular").lower()
    if session not in {"pre", "post"}:
        return False
    if quote.price is None or quote.previous_close is None:
        return False
    gap = abs(float(quote.price) - float(quote.previous_close))
    if swing.use_atr:
        atr = compute_atr(quote.ticker, period=swing.atr_period)
        if atr and atr > 0:
            return gap >= swing.atr_target_mult * atr
    return gap >= float(quote.previous_close) * (swing.target_pct / 100.0)


_EARNINGS_RISK_TIPOS = {"extended_hours", "news", "peer_lag", "momentum", "price_spike"}
_EARNINGS_RISK_HOURS = 72


def _earnings_within_hours(
    ticker: str,
    earnings: list[EarningsEvent],
    now: datetime,
    *,
    hours: int = _EARNINGS_RISK_HOURS,
) -> bool:
    horizon = now + timedelta(hours=hours)
    for ev in earnings:
        if ev.ticker.upper() != ticker.upper() or ev.reported:
            continue
        try:
            day = datetime.fromisoformat(ev.date).date()
        except ValueError:
            continue
        ev_when = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        if now <= ev_when <= horizon:
            return True
    return False


def _apply_earnings_risk(alert: Alert, earnings: list[EarningsEvent], now: datetime) -> Alert | None:
    if alert.tipo not in _EARNINGS_RISK_TIPOS or alert.ticker == "*":
        return alert
    if not _earnings_within_hours(alert.ticker, earnings, now):
        return alert
    if "RISK: Earnings in < 72h" not in alert.tags:
        alert.tags.append("RISK: Earnings in < 72h")
    alert.setup_score = 0
    alert.verdict = "BLOCCATO · utili imminenti"
    return None


def _news_score(item: NewsItem, rules: Rules) -> NewsItem | None:
    pub = _publisher_key(item)
    if any(block in pub for block in rules.news_block_publishers):
        return None
    text = item.headline.lower()
    if any(block in text for block in rules.news_block_headline):
        return None
    score = 0
    matched: list[str] = []
    for word, weight in rules.news_keywords:
        if word in text:
            score += weight
            matched.append(word)
    is_wire = any(boost in pub for boost in rules.news_boost_publishers)
    if is_wire:
        score += 2
        if "wire" not in matched:
            matched.append("wire")
    if rules.news_require_wire and not is_wire and score < rules.news_min_score + 2:
        return None
    opinion = any(name in pub for name in rules.news_opinion_publishers)
    if opinion:
        need = set(rules.news_opinion_need or ["upgrade", "downgrade", "guidance", "beat", "miss", "fda", "merger"])
        if not need.intersection(matched):
            return None
        score -= 1
    item.score = score
    item.matched = matched
    if score < rules.llm.prefilter_score and not is_wire:
        return None

    if rules.llm.enabled and llm_available():
        verdict = verify_news_catalyst(item, rules=rules.llm)
        if not verdict.approved:
            return None
        item.llm_driver = verdict.driver
        item.llm_provider = verdict.provider
        item.llm_unverified = verdict.unverified
        item.score = max(score, verdict.score)
    else:
        if score < rules.news_min_score:
            return None
        if len(matched) < 2 and not is_wire:
            return None
    return item


def _attach_swing(
    alert: Alert,
    *,
    cfg: AppConfig,
    quotes: dict[str, Quote],
    pct: float | None = None,
    news_score: int = 0,
    upside: bool = True,
    min_setup_score: int | None = None,
) -> Alert | None:
    floor = min_setup_score if min_setup_score is not None else cfg.rules.swing.min_setup_score
    quote = quotes.get(alert.ticker.upper()) if alert.ticker != "*" else None
    plan = build_swing_plan(
        tipo=alert.tipo,
        quote=quote,
        pct=pct,
        swing=cfg.rules.swing,
        news_score=news_score,
        upside=upside,
    )
    if plan is None:
        if alert.tipo == "earnings_soon":
            alert.setup_score = 4
            alert.verdict = "SOLO WATCHLIST"
            return alert if floor <= 4 else None
        return alert
    alert.setup_score = plan.score
    alert.verdict = plan.verdict
    if plan.entry_lo is not None and plan.entry_hi is not None:
        alert.entry_price = (plan.entry_lo + plan.entry_hi) / 2.0
    elif quote and quote.price is not None:
        alert.entry_price = float(quote.price)
    alert.target_price = plan.target
    alert.stop_price = plan.stop
    body = alert.body.rstrip()
    body += "\n\n" + "\n".join(plan.body_lines())
    alert.body = body
    if plan.score < floor:
        return None
    return alert


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _bucket(pct: float, buckets: list[float], minimum: float) -> float | None:
    abs_pct = abs(pct)
    if abs_pct < minimum:
        return None
    hit = minimum
    for b in sorted(buckets):
        if abs_pct >= b:
            hit = b
    return hit


def build_alerts(
    *,
    cfg: AppConfig,
    now: datetime,
    quotes: dict[str, Quote],
    earnings: list[EarningsEvent],
    news: list[NewsItem],
    filings: list[Filing],
    momentum: dict[str, float],
    min_setup_score: int | None = None,
) -> list[Alert]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = now.date()
    alerts: list[Alert] = []
    rules = cfg.rules
    only_up = rules.only_upside
    score_floor = min_setup_score if min_setup_score is not None else rules.swing.min_setup_score

    today_earn = [e for e in earnings if e.date == today.isoformat()]
    if today_earn:
        lines = []
        for ev in today_earn:
            mark = "RISULTATI FUORI" if ev.reported else _label(ev.hour)
            lines.append(f"• {ev.ticker} ({_name(cfg, ev.ticker)}) — {mark}")
        alerts.append(
            Alert(
                key=f"digest_earnings|{today.isoformat()}",
                tipo="digest_earnings",
                ticker="*",
                titolo="Oggi utili in watchlist",
                body="\n".join(lines),
                severity="medium",
            )
        )

    lookahead = now + timedelta(hours=rules.earnings_lookahead_hours)
    for ev in earnings:
        try:
            day = datetime.fromisoformat(ev.date).date()
        except ValueError:
            continue
        if day < today - timedelta(days=1) or day > lookahead.date():
            continue
        if ev.reported:
            eps_s = ev.eps_surprise_pct()
            rev_s = ev.revenue_surprise_pct()
            beat = False
            if eps_s is not None and abs(eps_s) >= rules.surprise_eps_pct:
                beat = True
            if rev_s is not None and abs(rev_s) >= rules.surprise_revenue_pct:
                beat = True
            if beat:
                upside = (eps_s or 0) > 0 or (rev_s or 0) > 0
                if only_up and not upside:
                    continue
                direction = "sopra stime" if upside else "sotto stime"
                hint = (
                    "Catalizzatore ufficiale post-utili: spesso muove pre/open."
                    if upside
                    else "Rischio gap ribassista."
                )
                price = quotes.get(ev.ticker.upper())
                px = f"${price.price:.2f}" if price and price.price else "n.d."
                alerts.append(
                    Alert(
                        key=f"earnings_surprise|{ev.ticker}|{ev.date}",
                        tipo="earnings_surprise",
                        ticker=ev.ticker,
                        titolo=f"{ev.ticker} — utili {direction}",
                        body=(
                            f"{_name(cfg, ev.ticker)} · ora {px}\n"
                            f"EPS {_fmt_eps(ev.eps_actual)} vs {_fmt_eps(ev.eps_estimate)} "
                            f"({_fmt_pct(eps_s)})\n"
                            f"Ricavi {_fmt_money(ev.revenue_actual)} vs {_fmt_money(ev.revenue_estimate)} "
                            f"({_fmt_pct(rev_s)})\n"
                            f"{hint}"
                        ),
                        severity="high",
                    )
                )
            continue
        when = "oggi" if day == today else day.isoformat()
        alerts.append(
            Alert(
                key=f"earnings_soon|{ev.ticker}|{ev.date}",
                tipo="earnings_soon",
                ticker=ev.ticker,
                titolo=f"{ev.ticker} — utili {when}",
                body=(
                    f"{_name(cfg, ev.ticker)} · {_label(ev.hour)}\n"
                    f"Stima EPS {_fmt_eps(ev.eps_estimate)} · ricavi {_fmt_money(ev.revenue_estimate)}\n"
                    "Volatilità in arrivo: tienilo in watchlist, non è un ingresso."
                ),
                severity="medium",
            )
        )

    for ticker, quote in quotes.items():
        if quote.halted:
            continue
        pct = quote.pct_from_close()
        if pct is None:
            continue
        if only_up and pct <= 0:
            continue
        session = (quote.session or "regular").lower()
        if session in {"pre", "post"} and abs(pct) >= rules.extended_hours_pct:
            if _gap_exceeds_atr_target(quote, rules.swing):
                continue
            if not _passes_rvol(quote, rules):
                continue
            if not _passes_dollar_volume(quote, cfg, rules):
                continue
            label = "pre-market" if session == "pre" else "after-hours"
            bucket = _bucket(pct, rules.spike_buckets, rules.extended_hours_pct) or rules.extended_hours_pct
            price = f"${quote.price:.2f}" if quote.price is not None else "n.d."
            rvol_txt = f"RVOL {quote.rvol:.1f}x" if quote.rvol is not None else "RVOL n.d."
            dv_txt = (
                f"${quote.dollar_volume / 1_000_000:.2f}M"
                if quote.dollar_volume and quote.dollar_volume >= 1_000_000
                else f"${quote.dollar_volume:,.0f}" if quote.dollar_volume else "n.d."
            )
            alerts.append(
                Alert(
                    key=f"ext|{ticker}|{today.isoformat()}|{session}|up|{int(bucket)}",
                    tipo="extended_hours",
                    ticker=ticker,
                    titolo=f"{ticker} — {pct:+.1f}% {label}",
                    body=(
                        f"{_name(cfg, ticker)} {price} · {rvol_txt} · {dv_txt} scambiati\n"
                        "Gap fuori seduta con volume e liquidità sufficienti.\n"
                        "Valuta ingresso solo se il movimento non è già eccessivo."
                    ),
                    severity="high" if abs(pct) >= 3 else "medium",
                )
            )
            continue
        bucket = _bucket(pct, rules.spike_buckets, rules.spike_pct)
        if bucket is None:
            continue
        if not _passes_rvol(quote, rules, for_spike=True):
            continue
        price = f"${quote.price:.2f}" if quote.price is not None else "n.d."
        alerts.append(
            Alert(
                key=f"spike|{ticker}|{today.isoformat()}|up|{int(bucket)}",
                tipo="price_spike",
                ticker=ticker,
                titolo=f"{ticker} {pct:+.1f}% dalla chiusura precedente",
                body=(
                    f"{_name(cfg, ticker)} {price} (fonte {quote.source})\n"
                    f"Soglia: {bucket:.0f}%.\n"
                    "Attenzione: in seduta è spesso 'già salito', non anticipo."
                ),
                severity="high" if abs(pct) >= 5 else "medium",
            )
        )

    for cluster in cfg.clusters:
        members = [t for t in cluster.tickers if t in quotes]
        if len(members) < 2:
            continue
        scored = []
        for ticker in members:
            pct = quotes[ticker].pct_from_close()
            if pct is None:
                continue
            scored.append((ticker, pct))
        if not scored:
            continue
        if only_up:
            leaders = [(t, p) for t, p in scored if p >= rules.peer_lag_leader_pct]
            if not leaders:
                continue
            leader, lead_pct = max(leaders, key=lambda x: x[1])
        else:
            leader, lead_pct = max(scored, key=lambda x: abs(x[1]))
            if abs(lead_pct) < rules.peer_lag_leader_pct:
                continue
        leader_q = quotes.get(leader)
        if leader_q is not None:
            min_rvol = rules.volume.peer_leader_min_rvol
            if leader_q.rvol is not None and leader_q.rvol < min_rvol:
                continue
            if leader_q.rvol is None and rules.volume.require_for_extended:
                continue
        laggards = [
            (t, p)
            for t, p in scored
            if t != leader and abs(p) < rules.peer_lag_max_pct
        ]
        if not laggards:
            continue
        pick, pick_pct = laggards[0]
        lag_txt = ", ".join(f"{t} {_fmt_pct(p)}" for t, p in laggards)
        pick_q = quotes.get(pick)
        if pick_q and pick_q.halted:
            continue
        if pick_q and not _passes_dollar_volume(pick_q, cfg, rules, for_peer=True):
            continue
        resist = None
        if rules.peer_resistance and pick_q and pick_q.price:
            resist = nearest_resistance(pick, pick_q.price)
        rvol_note = ""
        if leader_q and leader_q.rvol is not None:
            rvol_note = f" · RVOL leader {leader_q.rvol:.1f}x"
        alerts.append(
            Alert(
                key=f"peer|{cluster.name}|{leader}|{pick}|{today.isoformat()}",
                tipo="peer_lag",
                ticker=pick,
                titolo=f"{pick} — catch-up vs {leader} ({cluster.name})",
                body=(
                    f"{leader} {_fmt_pct(lead_pct)}{rvol_note} · {pick} {_fmt_pct(pick_pct)} · altri: {lag_txt}\n"
                    f"Resistenza vicina: {fmt_resistance(resist)}\n"
                    "Peer in ritardo con leader supportato da volume."
                ),
                severity="high",
            )
        )

    for ticker, pct in momentum.items():
        if abs(pct) < rules.momentum_pct:
            continue
        if only_up and pct <= 0:
            continue
        hour_bucket = now.strftime("%Y-%m-%dT%H")
        alerts.append(
            Alert(
                key=f"momentum|{ticker}|{hour_bucket}",
                tipo="momentum",
                ticker=ticker,
                titolo=f"{ticker} {pct:+.1f}% in {rules.momentum_minutes} min",
                body=(
                    f"{_name(cfg, ticker)} — movimento breve (barre 5 min).\n"
                    "Reazione immediata, spesso già in corso."
                ),
                severity="high" if abs(pct) >= 4 else "medium",
            )
        )

    for item in news:
        scored = _news_score(item, rules)
        if scored is None:
            continue
        ident = _hash(scored.url or scored.headline)
        tags = ", ".join(scored.matched[:6]) if scored.matched else "rilevante"
        pub = scored.publisher or scored.source
        driver = scored.llm_driver or "catalizzatore operativo"
        alert_tags: list[str] = []
        if scored.llm_unverified:
            alert_tags.append("LLM Unverified")
        alerts.append(
            Alert(
                key=f"news|{scored.ticker}|{ident}",
                tipo="news",
                ticker=scored.ticker,
                titolo=f"{scored.ticker} — catalizzatore wire",
                body=(
                    f"{scored.headline}\n"
                    f"{pub} · tag: {tags}\n"
                    f"Driver: {driver}"
                ),
                severity="high" if scored.score >= 7 else "medium",
                url=scored.url or None,
                tags=alert_tags,
            )
        )

    max_filing_days = max(1, (cfg.edgar.max_age_hours + 23) // 24)
    item_filter = [x.lower() for x in rules.filing_items_only]
    for filing in filings:
        try:
            filed = datetime.fromisoformat(filing.filed).date()
        except ValueError:
            continue
        if (now.date() - filed).days > max_filing_days:
            continue
        items = filing.items.strip() or "voci n.d."
        if item_filter and not any(tok in items.lower() for tok in item_filter):
            continue
        if "2.02" in items:
            item_label = "utili"
        elif "1.01" in items:
            item_label = "accordo materiale"
        elif "5.02" in items:
            item_label = "cambio management"
        elif "8.01" in items:
            item_label = "evento societario"
        else:
            item_label = items
        alerts.append(
            Alert(
                key=f"filing|{filing.ticker}|{filing.accession}",
                tipo="filing_8k",
                ticker=filing.ticker,
                titolo=f"{filing.ticker} — 8-K {item_label}",
                body=(
                    f"{_name(cfg, filing.ticker)} · deposito {filing.filed}\n"
                    f"Item SEC: {items}\n"
                    "Filing ufficiale ad alto impatto (utili, accordo, management o evento societario)."
                ),
                severity="high",
                url=filing.url,
            )
        )

    if rules.enabled_tipos:
        allowed = {t.lower() for t in rules.enabled_tipos}
        alerts = [a for a in alerts if a.tipo.lower() in allowed]

    finalized: list[Alert] = []
    for alert in alerts:
        pct = None
        if alert.ticker in quotes:
            pct = quotes[alert.ticker].pct_from_close()
        news_score = 0
        if alert.tipo == "news":
            for item in news:
                if item.ticker == alert.ticker:
                    news_score = max(news_score, item.score)
        kept = _attach_swing(
            alert,
            cfg=cfg,
            quotes=quotes,
            pct=pct,
            news_score=news_score,
            upside=True,
            min_setup_score=score_floor,
        )
        if kept is not None:
            kept = _apply_earnings_risk(kept, earnings, now)
        if kept is not None:
            finalized.append(kept)
    alerts = finalized

    order = [
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
    rank = {name: i for i, name in enumerate(order)}
    alerts.sort(key=lambda a: (rank.get(a.tipo, 99), a.ticker, a.key))
    return alerts
