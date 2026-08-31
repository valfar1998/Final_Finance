# PROJECT BRIEF — Finance Alert (FINANCE NOTIFY)

## Visione

Alert **Telegram** su eventi di borsa **verificabili** per swing trading (~7 giorni, target +2–3%): utili/surprise, gap pre/after-hours con volume, peer in ritardo, 8-K SEC ad alto impatto, news wire filtrate da **LLM**.

> Non è consiglio finanziario né previsione certa. Obiettivo: intercettare catalizzatori **prima** che il movimento sia assorbito — riducendo rumore con RVOL, LLM e dedupe semantico.

## Stack

- Python 3.11, PyYAML, urllib (no scraping HTML)
- Streamlit (`app.py`) per dry-run e preview
- GitHub Actions: **15 min** baseline + **3 min** in finestre ad alta volatilità (CET)
- LLM opzionale: **Groq** (Llama) o **Gemini Flash** per scoring news

## Flusso dati

```text
config/watchlist.yaml + .env
        │
aggregator (quote, earnings, news, filings — parallelo)
        │  overlay pre/post (Yahoo 5m) + RVOL sessione
        │
rules.build_alerts
        │  keyword prefilter → LLM verify (news)
        │  RVOL gate (extended/spike/peer leader)
        │  swing plan (entry/target/stop + score)
        │
dedupe: key + similarità headline (ticker + testo)
        │
format → Telegram FINANCE NOTIFY
        │
data/last_scan.json + telegram_alerts_sent.json (_meta headline)
```

## Struttura cartelle

```
finance-alert/
├── finance_alert/
│   ├── __main__.py          # CLI: --status, --dry-run, --test, scan
│   ├── engine.py            # Scan, dedupe semantico, persistenza
│   ├── aggregator.py        # Fallback multi-fonte + RVOL overlay
│   ├── rules.py             # Alert + filtri precisione
│   ├── swing.py             # Piano entry/target/stop
│   ├── news_llm.py          # Verifica catalizzatore (Groq/Gemini)
│   ├── dedupe.py            # Similarità headline Jaccard
│   ├── technical.py         # Resistenza da massimi 20g
│   ├── config.py / models.py / format.py / telegram.py
│   └── sources/
│       ├── finnhub.py       # Quote, earnings, news
│       ├── fmp.py / twelve.py / polygon.py
│       ├── yahoo.py         # Chart 5m, RVOL, RSS
│       ├── edgar.py         # 8-K SEC
│       └── benzinga.py / marketaux.py / newsapi.py
├── config/watchlist.yaml    # Megacap + mid-cap beta, cluster, soglie
├── scripts/notify_borsa.py
├── tests/
├── PROJECT_BRIEF.md         # ← questo file (aggiornare ad ogni change set)
└── .github/workflows/
```

## Fonti dati

| Fonte | API key? | Uso |
|-------|----------|-----|
| **Finnhub** | Sì | Quote, earnings, news |
| **FMP / Twelve / Polygon** | Opz. | Fallback batch quote/news |
| **Yahoo chart/RSS** | No | Pre/post 5m, **RVOL**, RSS |
| **SEC EDGAR** | No | 8-K Item **2.02** e **1.01** only |
| **Benzinga / Marketaux / NewsAPI** | Opz. | Wire news |
| **Groq / Gemini** | Opz. | Filtro LLM news |

Catena quote: FMP → Twelve → Finnhub → Polygon → Yahoo.

## Tipi alert

| `tipo` | Quando | Filtri precisione |
|--------|--------|-------------------|
| `earnings_surprise` | EPS/ricavi vs stime | swing score |
| `filing_8k` | 8-K Item 2.02 / 1.01 | esclusi item routine |
| `extended_hours` | Gap pre/post ≥ soglia | **RVOL ≥ 3x** |
| `peer_lag` | Leader su, laggard fermo | leader **RVOL ≥ 2.5x**, resistenza |
| `news` | Wire + keyword prefilter | **LLM approve** (se key presente) |
| `price_spike` / `momentum` | Spenti in YAML | RVOL se riattivati |

Solo setup **≥ min_setup_score** (default 6/10) vengono inviati.

## Watchlist

**Megacap:** NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AMD, AVGO, SMCI  
**Mid-cap beta:** PLTR, COIN, SOFI, MARA, HOOD  
**Cluster:** `semis`, `megacap`, `high_beta`

## Latenza (GitHub Actions)

| Finestra | Cron (UTC) | Frequenza |
|----------|------------|-----------|
| Lun–ven baseline | `*/15 8-23` | ogni 15 min |
| Alta vol CET 14:00–15:30 | `*/3 12-13` | ogni 3 min |
| Alta vol CET 22:00–22:30 | `*/3` min a h20 | ogni 3 min |
| Sab–dom | ore pari 8–22 | ogni 2 h |

**Collo di bottiglia:** GitHub Actions non è real-time. Per latenza &lt;1 min servirebbe worker continuo (Render/Railway) — fuori scope attuale ma documentato.

## Stato persistente

| File | Contenuto |
|------|-----------|
| `data/telegram_alerts_sent.json` | Dedupe 21g: key + `_meta` (ticker, headline, tipo) |
| `data/last_scan.json` | Ultimo scan |
| `data/cik_cache.json` | Ticker → CIK |

Dedupe semantico: Jaccard ≥ 0.72 su headline normalizzata per stesso ticker.

## Comandi

```powershell
python -m finance_alert --status
python -m finance_alert --dry-run
python -m finance_alert --test
python -m finance_alert
streamlit run app.py
```

## Secrets GitHub

Obbligatori: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `FINNHUB_API_KEY`  
Consigliati: `GROQ_API_KEY` o `GEMINI_API_KEY`, `SEC_CONTACT_EMAIL`  
Opzionali: FMP, Twelve, Polygon, Benzinga, Marketaux, NewsAPI

## Non in scope

- Trading automatico / ordini broker
- Previsione direzione prima della notizia
- Worker 24/7 a pagamento (solo documentato come upgrade)

## Changelog recente

- **2026-08-31:** LLM news scoring, RVOL filter, dedupe semantico, 8-K 2.02/1.01 only, peer-lag + resistenza, mid-cap watchlist, cron 3 min finestre volatili, PROJECT_BRIEF aggiornato.
