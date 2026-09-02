# PROJECT BRIEF — Finance Analyzer

## Visione

Dashboard **azioni / ETF / startup** con analisi quantitativa: prezzi storici, CAGR, volatilità, max drawdown, **Monte Carlo** forecast, rating analisti, filtri “startup pick”. Frontend Next.js + backend FastAPI con cache SQLite.

## Stack

| Layer | Tecnologia |
|-------|------------|
| Frontend | Next.js, React, Recharts, TypeScript |
| Backend | FastAPI, uvicorn |
| Dati mercato | Stooq, Yahoo Finance, Finnhub |
| Cache | SQLite (`cache_db`) |
| Env | `.env` con API keys (Finnhub, FMP, Twelve, …) |

## Architettura

```text
Browser localhost:3000
        │
        ▼
FastAPI backend/main.py (:8000)
        │
├── services/market_data.py     # Prezzi close (Stooq → Yahoo fallback)
├── services/analytics.py         # CAGR, YTD, vol, max DD, chart
├── services/forecast.py          # Monte Carlo (2000–5000 sim)
├── services/cache_db.py          # SQLite cache analisi
├── services/universe.py          # Sync ETF/universo simboli
├── services/startups.py          # Filtri startup featured
└── assets.py / REGIONS           # Metadati asset
```

## Struttura cartelle

```
Finance-Analyzer-main/
├── backend/
│   ├── main.py              # FastAPI app + endpoints
│   ├── load_env.py          # Bootstrap .env
│   ├── assets.py            # DEFAULT_ASSETS, REGIONS
│   ├── services/
│   │   ├── market_data.py
│   │   ├── analytics.py
│   │   ├── forecast.py
│   │   ├── cache_db.py
│   │   ├── universe.py
│   │   ├── startups.py
│   │   └── analyst_dates.py
│   └── scripts/sync_stooq.py
├── frontend/
│   ├── app/                 # Next.js App Router
│   ├── package.json
│   └── ...
└── .env                     # FINNHUB_API_KEY, ecc.
```

## Endpoint principali (backend)

| Route | Funzione |
|-------|----------|
| `GET /api/assets` | Lista asset paginata |
| `GET /api/analyze/{id}` | Analisi completa (chart, forecast, analyst) |
| `GET /api/startups` | Ricerca startup da cache |
| `POST /api/sync` | Sync universo ETF/simboli |

Analisi cached per `asset["id"]` — evita ricalcolo Stooq/Yahoo ad ogni richiesta.

## Fonti dati

| Fonte | Uso |
|-------|-----|
| **Stooq** | Prezzi storici close (primario) |
| **Yahoo Finance** | Fallback ticker + nome display |
| **Finnhub** | Recommendation analisti, target price |

`sync_stooq.py` / `sync_universe()` popolano il DB simboli.

## Metriche calcolate

- CAGR annuo, YTD, volatilità annualizzata, max drawdown
- Monte Carlo: distribuzione prezzo futuro, percentili
- `get_analyst_buyability()` — consensus vs prezzo corrente
- Startup: spread target, filtri `passes_startup_filters`

## Avvio

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev    # localhost:3000
```

CORS abilitato per `localhost:3000`.

## Relazione con altri progetti

- **`finance-alert`**: legge le stesse API keys da `.env` sibling se mancanti
- **`stock_analysis`**: approccio complementare (HTML TIKR vs API quantitativa)

## Non in scope

- Esecuzione ordini broker
- Dati fondamentali completi (bilanci SEC) — focus prezzo + analisti
- Auth multi-utente

## Portafoglio + alert Telegram (nuovo)

| Endpoint / script | Funzione |
|-------------------|----------|
| `GET/POST/DELETE /api/portfolio` | Portafoglio persistente SQLite |
| `POST /api/portfolio/scan` | Ricalcolo buyability + alert Telegram |
| `python scripts/scan_portfolio_alerts.py` | CLI scan portafoglio |

Variabili: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `FA_SCORE_ALERT_MIN_DELTA` (default 5 pp).
