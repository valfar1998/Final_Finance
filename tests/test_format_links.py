from finance_alert.format import format_alerts
from finance_alert.models import Alert
from finance_alert.config import Ticker
from finance_alert.sources import wire_rss
from finance_alert.tr_universe import NameMatcher, TrInstrument


def test_format_includes_tradingview_and_source_links():
    alert = Alert(
        key="news|NVDA|x",
        tipo="news",
        ticker="NVDA",
        titolo="NVDA — test",
        body=(
            "NVIDIA raised guidance after beat estimates\n"
            "Prezzo 120.00 (+2.0% vs close) · sessione post\n"
            "Fonte: PR Newswire · parole-chiave: guidance, wire\n"
            "Motivo tecnico: guidance raised\n\n"
            "Setup swing: 7/10 · INTERESSANTE\n"
            "Ingresso ideale: $119.00–$121.00\n"
            "Target 7g: $123.00 (+2.5% da ingresso)\n"
            "Stop: $115.00 (-3.7% da ingresso)\n"
            "Orizzonte ~7 giorni · obiettivo +2.5% (non garantito)."
        ),
        url="https://example.com/pr",
        setup_score=7,
        verdict="INTERESSANTE",
        tags=["LLM Unverified"],
        entry_price=120.0,
        target_price=123.0,
        stop_price=115.0,
    )
    text = format_alerts([alert], with_unified=False)
    assert "tradingview.com/chart/?symbol=NVDA" in text
    assert "https://example.com/pr" in text
    assert "Cosa è successo" in text
    assert "Perché è segnalato" in text
    assert "Cosa fare" in text
    assert "NVIDIA raised guidance" in text
    assert "Setup swing: 7/10" in text


def test_format_gap_explains_why():
    alert = Alert(
        key="ext|AMD|x",
        tipo="extended_hours",
        ticker="AMD",
        titolo="AMD — +1.6% after-hours",
        body=(
            "Advanced Micro Devices a $512.44 in after-hours (+1.6% vs chiusura).\n"
            "Volume relativo RVOL 40.6x, liquidità circa $92.21M.\n"
            "Fatto: gap fuori seduta con scambi sufficienti per uno swing breve.\n\n"
            "Setup swing: 7/10 · INTERESSANTE\n"
            "Ingresso ideale: $509.88–$517.56\n"
            "Target 7g: $513.67 (+0.0% da ingresso)\n"
            "Stop: $492.29 (-3.4% da ingresso)"
        ),
        setup_score=7,
        verdict="INTERESSANTE",
        entry_price=513.72,
        target_price=513.67,
        stop_price=492.29,
    )
    text = format_alerts([alert], with_unified=False)
    assert "gap fuori seduta" in text.lower() or "fuori dalla seduta" in text.lower()
    assert "non un ordine automatico" in text.lower() or "non è un consiglio" in text.lower()


def test_wire_does_not_map_corp_v_to_visa():
    watch = [Ticker(ticker="V", name="Visa")]
    assert (
        wire_rss._resolve_headline_ticker(
            "Haymaker Acquisition Corp V Announces Pricing of $250,000,000 Initial Public Offering",
            watch,
            use_tr=False,
        )
        is None
    )


def test_wire_prefers_nasdaq_ticker_and_unescapes_amp():
    watch = [Ticker(ticker="AMP", name="Ameriprise"), Ticker(ticker="FSHP", name="Flag Ship")]
    # HTML entity must not become AMP; explicit NASDAQ ticker wins.
    hit = wire_rss._resolve_headline_ticker(
        "$HAREHOLDER ALERT: The M&amp;A Class Action Firm Announces An Investigation "
        "of Flag Ship Acquisition Corporation (NASDAQ: FSHP)",
        watch,
        use_tr=False,
    )
    assert hit == "FSHP"


def test_name_matcher_ignores_amp_entity_and_short_tickers():
    instruments = [
        TrInstrument(isin="US03076C1062", name="Ameriprise Financial", ticker="AMP"),
        TrInstrument(isin="US92826C8394", name="Visa", ticker="V"),
        TrInstrument(isin="US0000000001", name="Flag Ship Acquisition", ticker="FSHP"),
    ]
    matcher = NameMatcher(instruments, min_name_len=4)
    assert matcher.match("M&amp;A Class Action Firm investigates something") is None
    assert matcher.match("Haymaker Acquisition Corp V Announces Pricing") is None
    hit = matcher.match("Flag Ship Acquisition Corporation (NASDAQ: FSHP) update")
    assert hit is not None and hit.ticker == "FSHP"
