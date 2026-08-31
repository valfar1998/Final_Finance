# PROJECT BRIEF — Finance Alert (FINANCE NOTIFY)

## Visione

Alert **Telegram** su eventi di borsa **verificabili** per swing trading (~7 giorni, target +2–3%): utili/surprise, gap pre/after-hours con volume e liquidità, peer in ritardo, 8-K SEC ad alto impatto, news wire filtrate da **LLM**.

> Non è consiglio finanziario. Obiettivo: catalizzatori verificabili con meno rumore e link rapidi per agire.

## Stack

- Python 3.11, PyYAML, urllib (no scraping HTML)
- Streamlit (`app.py`) per dry-run e preview
- GitHub Actions: 15 min baseline + **3 min** finestre volatili + cache RVOL
- LLM opzionale: **Groq** / **Gemini Flash** (timeout 3s + fallback keyword)

## Flusso dati

```text
config/watchlist.yaml + .env
        │
ensure_baseline() → data/rvol_baseline.json (1×/giorno, profilo 20g 5m)
        │
aggregator (quote, earnings, news, filings)
        │  overlay pre/post (Yahoo 1d) + RVOL da cache
        │  macro SPY/QQQ
        │
rules.build_alerts
        │  RVOL ≥ 3x + dollar volume gate
        │  LLM JSON is_catalyst / impact_score
        │  min_setup_score 6 (8 se mercato stress)
        │
dedupe semantico + format (TradingView + fonte SEC/news)
        │
Telegram FINANCE NOTIFY
```

## Moduli chiave

| Modulo | Ruolo |
|--------|--------|
| `rvol_baseline.py` | Cache volume medio 20g; scan usa solo chart **1d** |
| `macro.py` | SPY/QQQ stress → soglia setup 8/10 |
| `news_llm.py` | LLM 3s timeout; fallback keyword ≥8 `[LLM Unverified]` |
| `dedupe.py` | Similarità headline Jaccard |
| `technical.py` | Resistenza da massimi 20g |
| `swing.py` | Entry / target / stop |

## Filtri precisione

| Filtro | Soglia default |
|--------|----------------|
| RVOL | ≥ 3× (baseline cache) |
| Dollar volume pre/AH | ≥ $250k (megacap), ≥ $500k (high_beta) |
| 8-K SEC | Solo Item **2.02** e **1.01** |
| News LLM | `is_catalyst` + `impact_score` ≥ 6 |
| Macro stress | SPY o QQQ ≤ −1.5% → setup min **8/10** |
| Dedupe | Jaccard headline ≥ 0.72 |

## Watchlist

**Megacap:** NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AMD, AVGO, SMCI  
**Mid-cap beta:** PLTR, COIN, SOFI, MARA, HOOD  
**Cluster:** `semis`, `megacap`, `high_beta`

## Latenza (GitHub Actions)

| Finestra | Cron (UTC) | Frequenza |
|----------|------------|-----------|
| Lun–ven baseline | `*/15 8-23` | 15 min |
| Alta vol CET 14:00–15:30 | `*/3 12-13` | 3 min |
| Alta vol CET 22:00–22:30 | min 0–30 h20 | 3 min |
| Digest + baseline refresh | `30 11` lun–ven | ~13:30 CET |
| Sab–dom | ore pari 8–22 | 2 h |

**Rate limit Yahoo:** baseline 1×/giorno; scan frequenti leggono solo barre 1d. Cache Actions su `rvol_baseline.json`.

## Messaggio Telegram

Ogni alert include:
- Setup score / verdetto swing
- **Chart:** `https://www.tradingview.com/chart/?symbol=TICKER`
- **SEC filing** o **Fonte** (URL originale)
- Tag `[LLM Unverified]` se LLM in timeout

## Stato persistente

| File | Contenuto |
|------|-----------|
| `data/rvol_baseline.json` | Profilo volume 20g per ticker/sessione/slot |
| `data/telegram_alerts_sent.json` | Dedupe + `_meta` headline |
| `data/last_scan.json` | Ultimo scan |

## Comandi

```powershell
python -m finance_alert --status
python -m finance_alert --dry-run
python -m finance_alert --test
streamlit run app.py
```

## Secrets GitHub

Obbligatori: `TELEGRAM_*`, `FINNHUB_API_KEY`  
Consigliati: `GROQ_API_KEY` o `GEMINI_API_KEY`, `SEC_CONTACT_EMAIL`

## Non in scope

- Trading automatico
- Worker 24/7 continuo (documentato come upgrade)

## Changelog

- **2026-08-31 (b):** Cache RVOL giornaliera, dollar volume gate, filtro macro SPY/QQQ, LLM timeout 3s + fallback, link TradingView/fonte.
- **2026-08-31 (a):** LLM news, RVOL, dedupe semantico, mid-cap watchlist, cron 3 min.
