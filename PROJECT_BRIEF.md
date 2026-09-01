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
| Scheduler primario | **Modal.com** (scan ogni 60s finestre volatili) | $30/mese crediti free |
| Scheduler backup | GitHub Actions (15 min + 3 min) | gratuito |
| Dedupe | Upstash Redis REST + fallback file | free tier |
| Quote / earnings / news | Finnhub | free tier |
| Wire RSS | PR Newswire + GlobeNewswire | gratuito |
| LLM news | Groq o Gemini Flash (JSON mode) | free tier |
| Filing | SEC EDGAR API + Atom backup | gratuito |
| Performance | `performance_tracker.py` | locale / Redis |

## Flusso dati

```text
config/watchlist.yaml + .env
        │
ensure_baseline() → RVOL con media robusta (trimmed 10% / mediana)
        │
performance_tracker.update_forwards() → aggiorna +1/+3/+7g
        │
aggregator (quote, earnings, news, filings)
        │  wire RSS · overlay pre/post · RVOL · macro SPY/QQQ
        │  scarta quote halted (LULD / halt)
        │
rules.build_alerts
        │  RVOL ≥ 3x · dollar volume · cap gap ATR
        │  earnings proximity gate (< 72h → blocco)
        │  LLM JSON · swing ATR + cap resistenza
        │
dedupe ibrida → Upstash Redis → Telegram FINANCE NOTIFY
        │
performance_tracker.record_sent() → audit trail
```

## Moduli chiave

| Modulo | Ruolo |
|--------|--------|
| `stats_util.py` | Media trimmed 10% / mediana per baseline RVOL outlier-resistant |
| `performance_tracker.py` | Forward-test +1/+3/+7g, win rate, R-R, aspettativa E |
| `rvol_baseline.py` | Cache volume 20g con baseline robusta |
| `http.py` | `get_feed()` UA browser per RSS/XML |
| `state_store.py` | Dedupe Upstash Redis |
| `sources/wire_rss.py` | PR Newswire + GlobeNewswire Earnings |
| `sources/edgar.py` | SEC API submissions + Atom 8-K backup |
| `news_llm.py` | LLM JSON mode + dedupe equivalenza |
| `dedupe.py` | Dedupe ibrida 2h + Jaccard/LLM |
| `technical.py` | ATR(14) + resistenza 20g |
| `swing.py` | Target/stop ATR + cap resistenza |
| `modal_app.py` | Deploy serverless Modal (60s nelle finestre volatili) |

## Filtri precisione

| Filtro | Soglia default |
|--------|----------------|
| RVOL | ≥ 3× su baseline **robusta** (trimmed 10%) |
| Dollar volume pre/AH | ≥ $250k (megacap), ≥ $500k (high_beta) |
| 8-K SEC | Item **2.02**, **1.01**, **5.02**, **8.01** |
| Earnings proximity | Utili entro **72h** → score 0, tag `[RISK: Earnings in < 72h]` |
| Halt / LULD | `quote.halted = true` → scarta extended_hours, RVOL, peer |
| News LLM | `is_catalyst` + score ≥ 6; timeout → catalizzatori primari |
| Macro stress | SPY/QQQ ≤ −1.5% → setup min **8/10** |
| Dedupe | Ticker + **2h** + (Jaccard ≥ 0.65 OR LLM) |
| Target swing | **min(P + 1.5×ATR, Resistenza_20g)** |
| Stop swing | **1.0 × ATR(14)** |

## RVOL baseline robusta

Problema: un giorno di utili straordinari gonfia la media semplice e abbassa il RVOL reale.

Soluzione: `RVOL = V_attuale / robust_avg(V_20g)` dove `robust_avg` usa **media trimmed 10%** (o mediana se < 5 campioni).

## Performance tracker (feedback loop)

File: `data/performance_tracker.json`

Per ogni alert inviato salva entry, target, stop e aggiorna prezzi a **+1**, **+3**, **+7** giorni.

Metriche calcolate:
- **Win Rate %**
- **R-Ratio medio**
- **Aspettativa** \(E = P_{win} \times Target_{medio} - P_{loss} \times Stop_{medio}\)

## Fonti dati (produzione)

### Wire RSS

| Fonte | URL |
|-------|-----|
| PR Newswire | `https://www.prnewswire.com/rss/news-releases-list.rss` |
| GlobeNewswire Earnings | `…/subjectcode/27-Earnings%20Releases/…` |

### SEC EDGAR 8-K

| Fonte | Ruolo |
|-------|-------|
| API `submissions/CIK{cik}.json` | Primaria (filtri item) |
| Atom `browse-edgar?type=8-K&output=atom` | Backup discovery |

## Watchlist

**Megacap:** NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AMD, AVGO, SMCI  
**Mid-cap beta:** PLTR, COIN, SOFI, MARA, HOOD  
**Cluster:** `semis`, `megacap`, `high_beta`

## Scheduling: Modal.com (consigliato)

GitHub Actions ha latenza 5–10 min nella coda. **Modal** offre ~$30/mese di crediti gratuiti.

```powershell
pip install -r requirements-modal.txt
modal secret create finance-alert TELEGRAM_BOT_TOKEN=... FINNHUB_API_KEY=...
modal deploy modal_app.py
```

| Job Modal | Cron (UTC) | Frequenza |
|-----------|------------|-----------|
| `scan_high_vol_morning` | `*/1 12-13` lun–ven | 60s (~14–15:30 CET) |
| `scan_high_vol_evening` | `*/1 20` lun–ven | 60s (~22:00 CET) |
| `scan_baseline` | `*/15 8-23` lun–ven | 15 min |

GitHub Actions resta come **backup** (`telegram-borsa-alerts.yml`).

## Edge cases

| Regola | Comportamento |
|--------|---------------|
| Cap gap pre-market | Scarta se \|ΔP\| ≥ 1.5×ATR |
| Target vs resistenza | `min(P + 1.5×ATR, Resistenza_20g)` |
| Fallback LLM | Solo catalizzatori primari a score 6 |
| Parsing Yahoo | Fallback Finnhub |
| RSS 403 | UA browser via `get_feed()` |
| Earnings < 72h | Blocco setup + tag rischio |
| Halt/LULD | Scarta quote non affidabili |

## Stato persistente

| Store | Contenuto |
|-------|-----------|
| Upstash Redis | Dedupe alert |
| `data/rvol_baseline.json` | Profilo volume robusto 20g |
| `data/performance_tracker.json` | Audit trail + forward test |
| `data/telegram_alerts_sent.json` | Fallback dedupe locale |
| `data/last_scan.json` | Ultimo scan (Streamlit) |

## Comandi

```powershell
python -m finance_alert --status
python -m finance_alert --dry-run
python -m finance_alert --test
streamlit run app.py
modal deploy modal_app.py
```

## Secrets

| Secret | Obbligatorio | Ruolo |
|--------|:---:|-------|
| `TELEGRAM_BOT_TOKEN` | ✓ | Invio alert |
| `TELEGRAM_CHAT_ID` | ✓ | Destinatario |
| `FINNHUB_API_KEY` | ✓ | Quote, earnings, news |
| `UPSTASH_REDIS_REST_URL/TOKEN` | consigliato | Dedupe |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | consigliato | LLM news |
| `SEC_CONTACT_EMAIL` | consigliato | User-Agent SEC |

## Changelog

- **2026-09-01 (f):** RVOL robusto (trimmed/median); performance_tracker; earnings gate 72h; halt filter; Modal.com deploy.
- **2026-09-01 (e):** SEC Atom backup; feed wire produzione.
- **2026-09-01 (a–d):** Upstash, ATR, dedupe ibrida, edge cases, wire RSS.
- **2026-08-31:** RVOL cache, macro filter, LLM news.
