# PROJECT BRIEF — Final Finance (Quant Platform Unificata)

> **Repository:** [valfar1998/Final_Finance](https://github.com/valfar1998/Final_Finance)  
> **Scopo:** ecosistema quantamentale gratuito che unisce alert Telegram intraday, scoring fondamentale, analisi quantitativa e controlli regolatori internazionali.  
> **Disclaimer:** tutti gli output (score, target, alert) sono strumenti informativi — **non consiglio finanziario**.

---

## 1. Visione e problema risolto

Il trading/investing informata richiede tre informazioni che di solito vivono in tool separati:

| Domanda | Modulo | Output |
|---------|--------|--------|
| **Quando** entrare? (catalizzatore, volume, gap) | FINANCE NOTIFY | Alert Telegram swing ~7 giorni |
| **Cosa** comprare? (qualità fondamentale) | Stock Analysis | Score 0–100 + verdetto + buy target |
| **Quanto** può rendere/volare? (prezzo storico, MC) | Finance Analyzer | CAGR, vol, Monte Carlo, buyability % |
| **È** regolato/sanzionato? | Regulatory Hub | Flag FCA/SEC/ESMA/AMF/… |

**Final Finance** risponde alle quattro domande in un'unica pipeline e arricchisce ogni alert Telegram con score unificato e prezzo di acquisto consigliato.

---

## 2. Struttura repository

```text
Final_Finance/
├── PROJECT_BRIEF.md              ← questo documento
├── README.md                     ← quick start
├── .env.example                  ← secrets FINANCE NOTIFY
├── requirements.txt              ← Python core (notify + unified)
├── requirements-modal.txt        ← deploy Modal.com (opzionale, non usato in prod)
├── modal_app.py                  ← scheduler Modal legacy (opzionale)
├── app.py                        ← Streamlit dashboard alert
│
├── config/
│   ├── watchlist.yaml            ← ticker monitorati + regole filtri
│   └── unified.yaml              ← score unificato, quality gate, screener
│
├── finance_alert/                ← MODULO 1: FINANCE NOTIFY + Quant Platform core
│   ├── __main__.py               ← CLI (--dry-run, --analyze, --screen, …)
│   ├── engine.py                 ← orchestratore scan
│   ├── aggregator.py             ← fetch quote/earnings/news/filings
│   ├── rules.py                  ← filtri precisione + swing plan
│   ├── format.py                 ← messaggi Telegram (arricchiti unified)
│   ├── enrich.py                 ← collegamento alert → analisi unificata
│   ├── telegram.py               ← invio bot Telegram
│   ├── analysis/                 ← scoring unificato
│   │   ├── fundamental.py        → bridge stock_analysis
│   │   ├── quantitative.py       → bridge finance_analyzer
│   │   ├── unified.py            → formula score 0–10
│   │   └── bridge.py
│   ├── regulatory/               ← API governative
│   │   ├── hub.py                ← router per regione ticker
│   │   ├── fca.py, fsa_edinet.py, amf.py, esma.py, bafin.py, consob.py
│   ├── db/store.py               ← SQLite quant_platform.db
│   └── sources/                  ← Finnhub, EDGAR, wire RSS, Yahoo, …
│
├── stock_analysis/               ← MODULO 2: scoring fondamentale
│   ├── scoring_engine.py         ← motore 0–100 per settore
│   ├── yahoo_api.py              ← fetch yfinance
│   ├── smart_money.py            ← bonus 13F Dataroma
│   ├── auto_analyze.py           ← CLI/API senza HTML
│   ├── portfolio_db.py           ← SQLite portafoglio
│   ├── telegram_notify.py        ← alert variazione score
│   └── app.py                    ← Flask UI :5055
│
├── finance_analyzer/             ← MODULO 3: dashboard quantitativa
│   ├── backend/                  ← FastAPI :8000
│   │   ├── main.py
│   │   ├── services/             ← analytics, forecast, market_data, portfolio
│   │   └── scripts/scan_portfolio_alerts.py
│   └── frontend/                 ← Next.js :3000
│
├── data/                         ← stato locale (gitignored parziale)
│   ├── quant_platform.db
│   ├── rvol_baseline.json
│   └── performance_tracker.json
│
└── .github/workflows/            ← GitHub Actions scheduler primario
    ├── telegram-borsa-alerts.yml
    └── keepalive.yml
```

---

## 3. Architettura end-to-end

```text
                         ┌─────────────────────────────────────┐
                         │  config/watchlist.yaml              │
                         │  config/unified.yaml                │
                         │  .env (TELEGRAM, FINNHUB, FCA, …)   │
                         └──────────────┬──────────────────────┘
                                        │
    ┌───────────────────────────────────┼───────────────────────────────────┐
    │                    FINANCE NOTIFY (scheduler)                         │
    │  GitHub Actions 15m/3m  │  python -m finance_alert (locale)           │
    └───────────────────────────────────┬───────────────────────────────────┘
                                        │
                    engine.run_scan()
                         │
         ┌──────────────────────────────┼──────────────────────────────┐
         │                              │                              │
         ▼                              ▼                              ▼
   fetch_quotes                  fetch_earnings                  fetch_news
   (Finnhub/Yahoo)               (Finnhub/FMP)                   (Finnhub + wire RSS)
         │                              │                              │
         └──────────────────────────────┼──────────────────────────────┘
                                        │
                              fetch_filings (SEC EDGAR 8-K)
                                        │
                              overlay: RVOL, extended hours, macro SPY/QQQ
                                        │
                              rules.build_alerts()  ← filtri restrittivi
                                        │
                              filter_fresh()        ← dedupe Redis/file
                                        │
                              filter_alerts()       ← quality gate unified (opz.)
                                        │
                              enrich_alert()        ← score + buy target
                                        │
                              format_alerts()       ← testo Telegram
                                        │
                              telegram.send_message()
                                        │
                              performance_tracker.record_sent()
```

### 3.1 Analisi on-demand (parallela agli alert)

```text
python -m finance_alert --analyze NVDA
        │
        ├── fundamental.py → stock_analysis/scoring_engine (Yahoo only)
        ├── quantitative.py → finance_analyzer/services (CAGR, MC, buyability)
        └── regulatory/hub.py → FCA/AMF/ESMA/… per suffisso ticker
        │
        └── unified.py → score 0–10 + buy target → SQLite + stdout
```

---

## 4. MODULO 1 — FINANCE NOTIFY (alert intraday)

### 4.1 Tipi di alert (`Alert.tipo`)

| Tipo | Trigger | Priorità swing |
|------|---------|----------------|
| `earnings_surprise` | EPS/revenue surprise > soglia | Alta |
| `filing_8k` | SEC 8-K item 2.02/1.01/5.02/8.01 | Alta |
| `extended_hours` | Gap pre/AH ≥ 1.5% + RVOL + $ volume | Alta |
| `peer_lag` | Leader cluster +4%, peer < +1% | Media |
| `news` | Wire + LLM catalizzatore score ≥ soglia | Media |
| `earnings_soon` | Utili entro N ore (watchlist) | Informativo |
| `price_spike` / `momentum` | Disabilitati in modalità `only_upside` | Bassa |

### 4.2 Pipeline filtri (`rules.py`)

Ogni alert potenziale passa **tutti** i filtri attivi. Se uno fallisce → silenziato.

| Filtro | Parametro YAML | Valore attuale (produzione) |
|--------|----------------|----------------------------|
| RVOL minimo | `rules.volume.min_rvol` | **3.0** |
| LLM score min | `rules.llm.min_llm_score` | **6** |
| Dollar volume AH | `rules.volume.min_dollar_volume` | $250k |
| Dollar volume high-beta | `min_dollar_volume_high_beta` | $500k |
| Earnings gate 72h | `rules.earnings_gate_enabled` | **true** |
| News wire obbligatorio | `rules.news_require_wire` | true |
| News min score | `rules.news_min_score` | 7 |
| Macro stress | SPY/QQQ ≤ −1.5% → min setup 8 | attivo |
| Cap gap ATR | \|ΔP\| ≥ 1.5×ATR → scarta | attivo |
| Halt/LULD | `quote.halted` → scarta | attivo |

**Earnings gate:** se `earnings_gate_enabled: true` e utili entro 72h → `setup_score = 0`, alert scartato con tag `[RISK: Earnings in < 72h]`.

### 4.3 RVOL robusto

```text
RVOL = volume_attuale / robust_avg(volume_20_giorni)
```

`robust_avg` = media trimmed 10% (outlier-resistant). Cache in `data/rvol_baseline.json`.

### 4.4 Piano swing (target/stop)

Calcolato in `swing.py` + `technical.py`:

- **Target:** `min(prezzo + 1.5×ATR(14), resistenza_20g)`
- **Stop:** `prezzo − 1.0×ATR(14)`
- **Setup score:** 0–10 combinando tipo alert, RVOL, LLM, macro

### 4.5 Fonti dati notify

| Fonte | File | API key |
|-------|------|---------|
| Finnhub | `sources/finnhub.py` | `FINNHUB_API_KEY` ✓ |
| SEC EDGAR | `sources/edgar.py` | `SEC_CONTACT_EMAIL` |
| PR Newswire / GlobeNewswire | `sources/wire_rss.py` | — |
| Yahoo extended | `sources/yahoo.py` | — |
| LLM news filter | `news_llm.py` | `GROQ_API_KEY` o `GEMINI_API_KEY` |
| Dedupe | `state_store.py` | Upstash Redis (opz.) |

### 4.6 Watchlist attuale (19 ticker)

Megacap: NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AMD, AVGO, SMCI  
High-beta: PLTR, COIN, SOFI, MARA, HOOD, MSTR, RIOT, SOXL, BITO

Cluster in YAML: `semis`, `megacap`, `high_beta`.

### 4.7 Scheduling

| Canale | Frequenza | File |
|--------|-----------|------|
| **GitHub Actions** (primario) | 15 min baseline + 3 min finestre volatili | `.github/workflows/telegram-borsa-alerts.yml` |
| **Locale** | manuale | `python -m finance_alert` |
| **Modal.com** (opzionale) | 60s finestre volatili; 15m baseline | `modal_app.py` — richiede carta dopo free tier |

**Dedupe tra run GHA:** configurare `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` nei secrets GitHub. Senza Upstash, fallback su cache file (`data/telegram_alerts_sent.json`) ripristinata a ogni run.

Deploy Modal (solo se serve latenza 60s e accetti costo ~$1/mese):

```powershell
pip install -r requirements-modal.txt
modal secret create finance-alert TELEGRAM_BOT_TOKEN=... FINNHUB_API_KEY=...
modal deploy modal_app.py
```

---

## 5. MODULO 2 — Stock Analysis (fondamentale)

### 5.1 Scoring 0–100

Motore: `stock_analysis/scoring_engine.py`

Categorie (pesi base, override per settore REIT/BDC/FINANCIALS/TECH/…):

| Categoria | Max punti |
|-----------|-----------|
| Profitabilità | 15 |
| Valutazione | 15 |
| Salute finanziaria | 15 |
| Cash flow | 10 |
| Dividendo | 10 |
| Crescita | 10 |
| Margini/efficienza | 8 |
| Tecnico/momentum | 8 |
| Consenso analisti | 10 |
| Insider/institutional | 6 |
| Settore/contesto | 6 |
| Smart Money 13F | +0…+3 bonus |

**Verdetto:** COMPRA FORTE (≥80), COMPRA (≥60), NEUTRO (≥40), EVITA (≥20), EVITA FORTE (<20).

**Affidabilità:** servono ≥ 5/7 campi critici Yahoo (`price, pe, eps, market_cap, rev_growth, fcf, de`).

### 5.2 Buy target

Formula in `buy_target()`: min di:

- Sconto fondamentale (95%/90%/85%/75% del prezzo per fascia score)
- Target analisti × 0.92 (se ≥ 5 analisti)
- Cap valuation settoriale (BVPS, NAV, …)

Layer unified (`fundamental.py`) corregge target assurdi su growth stock (BVPS cap troppo basso).

### 5.3 Modalità auto (senza HTML)

```powershell
cd stock_analysis
python auto_analyze.py NVDA --add      # analizza + salva portafoglio
python auto_analyze.py --scan          # scan + Telegram se Δscore ≥ 3
```

API Flask (`:5055`):

- `GET /api/auto-analyze/<TICKER>`
- `GET/POST/DELETE /api/portfolio`
- `POST /api/portfolio/scan`

DB: `stock_analysis/data/stock_analysis.db`

---

## 6. MODULO 3 — Finance Analyzer (quantitativo)

### 6.1 Metriche calcolate

Backend FastAPI `finance_analyzer/backend/main.py`:

| Metrica | Modulo |
|---------|--------|
| CAGR annuo | `services/analytics.py` |
| YTD, volatilità, max drawdown | idem |
| Monte Carlo 30/252g | `services/forecast.py` |
| Buyability % analisti | `services/market_data.py` |
| Prezzi Stooq → Yahoo fallback | `services/stooq.py`, `yahoo.py` |

### 6.2 Avvio

```powershell
# Backend
cd finance_analyzer/backend
python -m venv .venv && .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd finance_analyzer/frontend
npm install && npm run dev    # localhost:3000
```

### 6.3 Portafoglio + alert

- `POST /api/portfolio?ticker=NVDA` — aggiungi ticker
- `POST /api/portfolio/scan?notify=true` — ricalcola buyability, alert Telegram se Δ ≥ 5 pp
- CLI: `python scripts/scan_portfolio_alerts.py`

DB: `finance_analyzer/backend/data/finance.db`

---

## 7. MODULO 4 — Regulatory Hub

Router: `finance_alert/regulatory/hub.py` — rileva regione dal suffisso ticker.

| Suffisso / regione | Autorità | Implementazione |
|--------------------|----------|-----------------|
| US (default) | SEC | `sources/edgar.py` (già in notify) |
| `.L` / `.IL` | UK FCA | REST API V0.1 |
| `.T` / `.TO` | JP FSA | EDINET API v2 |
| `.PA` | FR AMF | OpenDataSoft info-financiere |
| `.DE` / `.F` | DE BaFin | scraping portale |
| `.MI` | IT CONSOB | scraping elenchi pubblici |
| EU cross | ESMA | Solr sanctions + FIRDS |

**Penalty score unificato:** 0–3 punti se sanzioni/avvisi/disciplinary history.

### Secrets regolatori

```env
FCA_AUTH_EMAIL=...          # email registrata su register.fca.org.uk/Developer
FCA_API_KEY=...
FSA_EDINET_API_KEY=...      # disclosure2.edinet-fsa.go.jp
SEC_CONTACT_EMAIL=...
```

AMF, ESMA, BaFin, CONSOB → nessuna chiave (open data / scraping).

---

## 8. Score unificato (Quant Platform)

File: `finance_alert/analysis/unified.py`

### Formula

Con catalizzatore (alert attivo):

```text
unified = 0.50 × (fundamental/10) + 0.25 × quant_score + 0.25 × catalyst_score − regulatory_penalty
```

Senza catalizzatore (analisi statica):

```text
unified = 0.55 × (fundamental/10) + 0.45 × quant_score − regulatory_penalty
```

Clamp finale: **0–10**.

### Quality gate (opzionale)

In `config/unified.yaml`:

```yaml
unified:
  quality_gate_block: false   # true = silenzia alert se score fondamentale basso
  min_fundamental_score: 40   # 0–100
  min_unified_score: 5.0      # 0–10
```

### Esempio messaggio Telegram arricchito

```text
FINANCE NOTIFY — swing 2–3% / ~7 giorni
2026-09-02 16:30 Roma

📊 Quant Platform: score fondamentale + quant + regolatori.

Catalizzatore wire
NVDA — contratto gov · 8/10 · BUY
[body alert con target/stop ATR]

📊 Score unificato: 7.3/10
   Fondamentale: 76/100 | Quant: 7.0/10
   Verdetto: COMPRA
   🎯 Prezzo acquisto consigliato: $201.46
Chart: https://www.tradingview.com/chart/?symbol=NVDA
```

---

## 9. Configurazione completa

### 9.1 `config/watchlist.yaml`

Sezioni principali:

- `watchlist[]` — ticker, name, cik (SEC)
- `rules.enabled_tipos` — quali alert generare
- `rules.only_upside` — true = no spike/momentum tardivi
- `rules.swing.*` — ATR target/stop, min_setup_score
- `rules.volume.*` — RVOL, dollar volume
- `rules.llm.*` — soglie LLM news
- `rules.macro.*` — SPY/QQQ stress filter
- `rules.dedupe.*` — finestra 2h, Jaccard 0.65
- `rules.earnings_gate_enabled` — blocco 72h
- `clusters[]` — peer groups per catch-up
- `edgar.*` — form 8-K, max_age_hours

### 9.2 `config/unified.yaml`

- `unified.enabled` — arricchimento Telegram on/off
- `unified.enrich_telegram` — contesto score in messaggio
- `unified.screener_tickers[]` — ticker extra per `--screen`
- `unified.screener_min_score` — soglia watchlist dinamica DB

### 9.3 Variabili ambiente (`.env`)

| Variabile | Obbl. | Modulo |
|-----------|:-----:|--------|
| `TELEGRAM_BOT_TOKEN` | ✓ | Notify + Stock Analysis + Finance Analyzer |
| `TELEGRAM_CHAT_ID` | ✓ | idem |
| `FINNHUB_API_KEY` | ✓ | Notify, quote, earnings |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | ○ | LLM news filter |
| `SEC_CONTACT_EMAIL` | ○ | SEC User-Agent |
| `UPSTASH_REDIS_REST_URL/TOKEN` | ○ | Dedupe distribuita |
| `FCA_AUTH_EMAIL` + `FCA_API_KEY` | ○ | UK FCA |
| `FSA_EDINET_API_KEY` | ○ | Japan EDINET |
| `FMP_API_KEY` / `TWELVE_DATA_API_KEY` | ○ | Fallback Finance Analyzer |
| `SCORE_ALERT_MIN_DELTA` | ○ | Stock Analysis (default 3) |
| `FA_SCORE_ALERT_MIN_DELTA` | ○ | Finance Analyzer (default 5) |

Il loader `finance_alert/env.py` legge anche `.env` sibling e `finance_analyzer/.env`.

---

## 10. Database SQLite

### 10.1 `data/quant_platform.db` (Quant Platform)

| Tabella | Contenuto |
|---------|-----------|
| `ticker_scores` | Storico score unified per ticker/ts |
| `dynamic_watchlist` | Ticker promossi da screener |
| `alert_audit` | Alert inviati/scartati con score |

### 10.2 `stock_analysis/data/stock_analysis.db`

| Tabella | Contenuto |
|---------|-----------|
| `portfolio` | Ticker seguiti |
| `score_history` | Storico score fondamentale |

### 10.3 `finance_analyzer/backend/data/finance.db`

| Tabella | Contenuto |
|---------|-----------|
| `symbols` | Universo titoli/ETF |
| `analysis_cache` | Cache analisi JSON |
| `user_portfolio` | Portafoglio utente |
| `score_history` | Storico buyability |

---

## 11. CLI — tutti i comandi

### FINANCE NOTIFY / Quant Platform

```powershell
python -m finance_alert --status          # fonti + watchlist
python -m finance_alert --dry-run         # scan senza invio (debug filtri)
python -m finance_alert --test            # ping Telegram
python -m finance_alert                   # scan + invio
python -m finance_alert --analyze NVDA    # score unificato
python -m finance_alert --regulatory SAP.DE
python -m finance_alert --screen --update-watchlist
streamlit run app.py
pytest tests/
```

### Stock Analysis

```powershell
cd stock_analysis
python auto_analyze.py AAPL --add
python auto_analyze.py --scan
python app.py                             # Flask :5055
```

### Finance Analyzer

```powershell
cd finance_analyzer/backend
uvicorn main:app --port 8000
python scripts/scan_portfolio_alerts.py
```

---

## 12. Debug — perché zero notifiche

Checklist in ordine:

1. **`python -m finance_alert --dry-run`** — legge log: quale filtro scarta?
2. **Secrets GitHub** — `TELEGRAM_BOT_TOKEN`, `FINNHUB_API_KEY` (e opz. Upstash) configurati?
3. **Watchlist** — 19 ticker + screener globale; giornate senza catalizzatori = 0 alert normale
4. **Filtri produzione** — RVOL 3.0, LLM 6, earnings gate on; abbassare temporaneamente in YAML solo per test
5. **Macro stress** — mercato −1.5% → soglia setup 8/10
6. **Dedupe** — stesso ticker entro 2h silenziato

Per testare la catena Telegram: abbassare temporaneamente soglie in YAML, poi `--dry-run`, poi `--test`, poi scan reale.

---

## 13. Test automatici

```powershell
pytest tests/test_rules.py tests/test_unified_platform.py tests/test_production_upgrades.py
```

Copertura: RVOL robusto, earnings gate on/off, regulatory region detect, unified config load.

---

## 14. Costi (tier gratuito)

| Servizio | Costo |
|----------|-------|
| Finnhub free | 60 req/min |
| GitHub Actions | free public repo (scheduler primario) |
| Modal.com | opzionale (~$1/mese dopo free tier) |
| Telegram Bot API | gratis |
| Groq/Gemini Flash | free tier |
| SEC/AMF/ESMA/… | gratis |
| yfinance / Stooq | gratis (non ufficiale Yahoo) |

---

## 15. Roadmap / limiti noti

- [ ] BaFin/CONSOB: no API bulk ufficiale — scraping limitato
- [ ] EDINET: query per data, non per ticker diretto
- [ ] Yahoo chart: può dare 429 — fallback Finnhub
- [ ] HTML TIKR/Investing: opzionale per metriche niche (FFO, CET1)
- [ ] Quality gate unified: disattivato in debug (`quality_gate_block: false`)

---

## 16. Changelog unificazione

| Data | Change |
|------|--------|
| 2026-09-02 | Scheduler primario → **GitHub Actions** (Modal disattivato) |
| 2026-09-02 | Filtri produzione: RVOL 3.0, LLM 6, earnings gate on; doc Upstash |
| 2026-09-02 | Repo **Final_Finance**: unificazione 3 moduli + regulatory hub |
| 2026-09-02 | Quant Platform: enrich Telegram, unified score, SQLite |
| 2026-09-02 | Watchlist estesa: +MSTR/RIOT/SOXL/BITO + screener multi-mercato |
| 2026-09-02 | stock_analysis: auto_analyze, portfolio DB, Telegram score alerts |
| 2026-09-02 | finance_analyzer: portfolio API, scan_portfolio_alerts |
| 2026-09-01 | FINANCE NOTIFY: Modal, RVOL robusto, performance tracker |

---

*Documento generato per analisi AI/architettura — aggiornare quando cambiano soglie YAML o moduli.*
