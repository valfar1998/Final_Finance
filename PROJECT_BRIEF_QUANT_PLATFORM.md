# PROJECT BRIEF — Quant Platform (Unificato)

## Visione

Ecosistema **quantamentale** che unisce:

| Modulo | Progetto origine | Ruolo |
|--------|------------------|-------|
| **FINANCE NOTIFY** | `finance-alert` | Alert Telegram su catalizzatori (RVOL, 8-K, wire, LLM) |
| **Stock Analysis** | `stock_analysis` | Scoring fondamentale 0–100 + buy target |
| **Finance Analyzer** | `Finance-Analyzer-main` | Metriche quantitative (CAGR, vol, Monte Carlo) |
| **Regulatory Hub** | nuovo | SEC, FCA, FSA/EDINET, AMF, ESMA, BaFin, CONSOB |

Output: **notifiche Telegram arricchite** con score unificato 0–10 e prezzo di acquisto consigliato.

## Architettura

```text
config/watchlist.yaml + config/unified.yaml + .env
        │
┌───────┴───────────────────────────────────────────┐
│  FINANCE NOTIFY (engine.py) — invariato             │
│  wire · EDGAR · Finnhub · RVOL · LLM · dedupe       │
└───────┬───────────────────────────────────────────┘
        │ alert fresh
        ▼
enrich.py → analysis/unified.py
        │     ├── fundamental.py → stock_analysis (yfinance)
        │     ├── quantitative.py → yfinance + Monte Carlo
        │     └── regulatory/hub.py → FCA/AMF/ESMA/...
        ▼
format.py (Telegram arricchito) + db/store.py (SQLite)
```

## Regolatori integrati

| Autorità | Metodo | Chiave |
|----------|--------|--------|
| **SEC** | `sources/edgar.py` | `SEC_CONTACT_EMAIL` |
| **UK FCA** | REST API V0.1 | `FCA_API_KEY` + `FCA_AUTH_EMAIL` |
| **JP FSA** | EDINET API v2 | `FSA_EDINET_API_KEY` |
| **AMF** | OpenDataSoft info-financiere | gratis |
| **ESMA** | Solr sanctions + FIRDS | gratis |
| **BaFin** | HTML search portale | gratis (no bulk API) |
| **CONSOB** | HTML elenchi pubblici | gratis (no API ufficiale) |

## Score unificato

```
unified = 0.50 × (fundamental/10) + 0.25 × quant + 0.25 × catalyst − regulatory_penalty
```

- **fundamental**: 0–100 da `stock_analysis/scoring_engine.py` (solo Yahoo se no HTML)
- **quant**: 0–10 da CAGR, volatilità, max drawdown
- **catalyst**: setup_score alert FINANCE NOTIFY (0–10)
- **regulatory_penalty**: 0–3 se sanzioni/avvisi ESMA/CONSOB/FCA

## Comandi

```powershell
python -m finance_alert --dry-run          # alert + log (Telegram arricchito se unified enabled)
python -m finance_alert --analyze NVDA     # analisi completa score + buy target
python -m finance_alert --regulatory SAP.DE # check regolatori EU/DE
python -m finance_alert --screen           # screen watchlist + screener_tickers
python -m finance_alert --screen --update-watchlist  # aggiorna DB watchlist dinamica
```

## Configurazione

- `config/unified.yaml` — soglie quality gate, screener, ticker extra
- `data/quant_platform.db` — storico score + watchlist dinamica

## Secrets (.env)

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
FINNHUB_API_KEY=...
FCA_AUTH_EMAIL=...        # email registrata FCA Developer Portal
FCA_API_KEY=...
FSA_EDINET_API_KEY=...    # EDINET subscription key
SEC_CONTACT_EMAIL=...
```

## Prossimo passo (repo unificata)

Quando crei la nuova repository, copia:
- `finance_alert/` (completo)
- `stock_analysis/scoring_engine.py`, `yahoo_api.py`, `sectors.py`, `smart_money.py`
- `Finance-Analyzer-main/backend/services/analytics.py`, `forecast.py` (opzionale)

Oppure mantieni i bridge in `analysis/bridge.py` che puntano ai sibling finché restano nella stessa cartella `corsi/`.

## Non è consiglio finanziario

Tutti gli score e i prezzi target sono indicativi e basati su dati pubblici gratuiti.
