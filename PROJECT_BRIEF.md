# PROJECT BRIEF — Finance Alert (FINANCE NOTIFY)

## Visione

Alert **Telegram** su eventi di borsa **verificabili** per swing trading (~7 giorni): utili/surprise, gap pre/after-hours con volume e liquidità, peer in ritardo, 8-K SEC ad alto impatto, news wire filtrate da **LLM**.

Target e stop sono calcolati con **ATR** (non % fisso) per adattarsi alla volatilità di titoli high-beta come MARA, COIN, TSLA.

> Non è consiglio finanziario. Obiettivo: catalizzatori verificabili con meno rumore e link rapidi per agire.

## Stack (solo tier gratuiti)

| Componente | Servizio | Piano |
|------------|----------|-------|
| Runtime | Python 3.11 + PyYAML + urllib | — |
| Preview | Streamlit (`app.py`) | locale |
| Scheduler | GitHub Actions (15 min + 3 min volatili) | gratuito |
| Dedupe | Upstash Redis REST + fallback file | free tier |
| Quote / earnings / news | Finnhub | free tier |
| Wire RSS | PR Newswire + GlobeNewswire | gratuito |
| LLM news | Groq o Gemini Flash (JSON mode) | free tier |
| Filing | SEC EDGAR | gratuito |

Fonti a pagamento (FMP, Polygon, Benzinga, …) sono **opzionali** e non necessarie.

## Flusso dati

```text
config/watchlist.yaml + .env
        │
ensure_baseline() → data/rvol_baseline.json (1×/giorno, profilo 20g 5m)
        │
aggregator (quote, earnings, news, filings)
        │  wire RSS (PR Newswire / GlobeNewswire, get_feed + UA browser)
        │  overlay pre/post (Yahoo 5m → fallback Finnhub)
        │  momentum (Yahoo → fallback Finnhub)
        │  RVOL da cache
        │  macro SPY/QQQ
        │
rules.build_alerts
        │  RVOL ≥ 3x + dollar volume gate
        │  cap gap pre-market vs target ATR
        │  LLM JSON mode: is_catalyst / impact_score
        │  min_setup_score 6 (8 se mercato stress)
        │  swing: target min(1.5×ATR, resistenza 20g), stop 1.0×ATR
        │
dedupe ibrida (ticker + finestra 2h + Jaccard OR LLM)
        │  stato su Upstash Redis (no cache-miss GH Actions)
        │
format (TradingView + fonte SEC/news) → Telegram FINANCE NOTIFY
```

## Moduli chiave

| Modulo | Ruolo |
|--------|--------|
| `http.py` | `get_feed()` con User-Agent browser per RSS/XML (evita 403) |
| `state_store.py` | Persistenza dedupe su Upstash Redis (REST) o file locale |
| `sources/wire_rss.py` | Feed RSS gratuiti PR Newswire / GlobeNewswire |
| `sources/edgar.py` | SEC EDGAR con User-Agent obbligatorio (`Nome/email`) |
| `rvol_baseline.py` | Cache volume medio 20g; scan usa solo chart **1d** |
| `macro.py` | SPY/QQQ stress → soglia setup 8/10 |
| `news_llm.py` | LLM JSON mode; dedupe equivalenza; fallback catalizzatori primari |
| `dedupe.py` | Dedupe ibrida: ticker + finestra 2h + Jaccard ≥ 0.65 OR LLM |
| `technical.py` | ATR(14) da OHLC giornaliero; resistenza da massimi 20g |
| `swing.py` | Entry / target / stop (ATR + cap resistenza) |

## Filtri precisione

| Filtro | Soglia default |
|--------|----------------|
| RVOL | ≥ 3× (baseline cache) |
| Dollar volume pre/AH | ≥ $250k (megacap), ≥ $500k (high_beta) |
| 8-K SEC | Item **2.02**, **1.01**, **5.02**, **8.01** |
| News LLM | `is_catalyst` + `impact_score` ≥ 6; timeout → solo catalizzatori primari a score 6 |
| Macro stress | SPY o QQQ ≤ −1.5% → setup min **8/10** |
| Dedupe | Stesso ticker + finestra **2h** + (Jaccard ≥ **0.65** OR equivalenza LLM) |
| Target swing | **min(P + 1.5×ATR, Resistenza_20g)** (fallback: +2.5%) |
| Stop swing | **1.0 × ATR(14)** (fallback: −1.5%) |

## Fonti dati (produzione)

### Wire RSS — `wire_rss.py` + `get_feed()`

Endpoint stabili, fetch con User-Agent browser (non `Python-urllib/3.x`).

| Fonte | URL | Nel progetto |
|-------|-----|:---:|
| **PR Newswire** (generico) | `https://www.prnewswire.com/rss/news-releases-list.rss` | ✅ |
| **GlobeNewswire** (utili) | `https://www.globenewswire.com/RssFeed/subjectcode/27-Earnings%20Releases/feedTitle/GlobeNewswire%20-%20Earnings%20Releases` | ✅ |

Match automatico su ticker/nome watchlist. Cache in-memory 120s per scan.

### SEC EDGAR 8-K — `edgar.py` (API JSON, non RSS Atom)

| Fonte | URL | Nel progetto |
|-------|-----|:---:|
| Feed Atom globale SEC | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&…&output=atom` | ❌ |
| **API submissions per CIK** | `https://data.sec.gov/submissions/CIK{cik}.json` | ✅ |

L'API per-CIK è preferita: filtra solo ticker in watchlist, include campo `items` (1.01, 2.02, 5.02, 8.01), User-Agent obbligatorio con email (`SEC_CONTACT_EMAIL`).

### Altre fonti (fallback / complementari)

| Fonte | Ruolo |
|-------|-------|
| Finnhub (free) | Quote, earnings, news per ticker |
| Yahoo chart | Pre/post market, RVOL, ATR (fallback Finnhub su 403/parsing) |
| Groq / Gemini (free) | Filtro catalizzatore news + dedupe LLM |

## Filtri precisione

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

**Limitazione nota:** i cron GitHub Actions non garantiscono esecuzione al minuto esatto; la coda può ritardare di 5–10 minuti. Per alert tempestivi in pre/after-hours valutare Modal, Lambda + EventBridge o VPS.

**Rate limit Yahoo:** fallback trasparente su **Finnhub** se 403/429 o errori di parsing (`KeyError`, `JSONDecodeError`).

## Edge cases (logica produzione)

| Regola | Comportamento |
|--------|---------------|
| **Cap gap pre-market** | Scarta alert `extended_hours` se \|ΔP pre/post\| ≥ target ATR (1.5×ATR) |
| **Target vs resistenza** | `target = min(P_entry + 1.5×ATR, Resistenza_20g)`; se cap ≤ entry, alert scartato |
| **Fallback LLM timeout** | `[LLM Unverified]` solo con catalizzatori primari; generiche → score < 6, scartate |
| **Parsing Yahoo** | Eccezioni JSON attivano fallback Finnhub su quote, session e momentum |
| **RSS wire 403** | `get_feed()` usa UA browser + `Accept: application/rss+xml` |

## Messaggio Telegram

Ogni alert include:
- Setup score / verdetto swing
- Target e stop (ATR o % fallback)
- **Chart:** `https://www.tradingview.com/chart/?symbol=TICKER`
- **SEC filing** o **Fonte** (URL originale)
- Tag `[LLM Unverified]` se LLM in timeout

## Stato persistente

| Store | Contenuto | Note |
|-------|-----------|------|
| **Upstash Redis** | `finance-alert:telegram_alerts_sent` | Primario in CI (no cache-miss) |
| `data/telegram_alerts_sent.json` | Dedupe + `_meta` headline | Fallback locale / dev |
| `data/rvol_baseline.json` | Profilo volume 20g per ticker/sessione/slot | Cache Actions in CI |
| `data/last_scan.json` | Ultimo scan (Streamlit) | Solo locale |

## Comandi

```powershell
python -m finance_alert --status
python -m finance_alert --dry-run
python -m finance_alert --test
streamlit run app.py
```

## Secrets GitHub

| Secret | Obbligatorio | Ruolo |
|--------|:---:|-------|
| `TELEGRAM_BOT_TOKEN` | ✓ | Invio alert |
| `TELEGRAM_CHAT_ID` | ✓ | Destinatario |
| `FINNHUB_API_KEY` | ✓ | Quote, earnings, news, fallback Yahoo |
| `UPSTASH_REDIS_REST_URL` | consigliato | Dedupe persistence-safe |
| `UPSTASH_REDIS_REST_TOKEN` | consigliato | Dedupe persistence-safe |
| `GROQ_API_KEY` o `GEMINI_API_KEY` | consigliato | Filtro news + dedupe LLM |
| `SEC_CONTACT_EMAIL` | consigliato | User-Agent SEC EDGAR |

## Non in scope

- Trading automatico
- Worker 24/7 continuo (upgrade: Modal / Lambda / VPS)

## Changelog

- **2026-09-01 (d):** Feed produzione stabili: PR `news-releases-list.rss` + GlobeNewswire Earnings; brief fonti dati con mapping SEC API vs Atom.
- **2026-09-01 (c):** Feed wire RSS PR Newswire/GlobeNewswire (`wire_rss.py`, `get_feed()` con UA browser).
- **2026-09-01 (b):** Edge cases: cap gap pre-market, target cap resistenza, fallback LLM catalizzatori primari, parsing Yahoo→Finnhub.
- **2026-09-01 (a):** Upstash Redis; target/stop ATR; 8-K 5.02/8.01; dedupe ibrida; LLM JSON mode.
- **2026-08-31 (b):** Cache RVOL, dollar volume gate, macro SPY/QQQ, link TradingView/fonte.
- **2026-08-31 (a):** LLM news, RVOL, dedupe semantico, mid-cap watchlist, cron 3 min.
