# PROJECT BRIEF — Stock Analysis

## Visione

Tool di **scoring fondamentale** per singole azioni: combina **Yahoo Finance (API)** con HTML salvati da **Investing.com** e **TIKR** (SingleFile), applica metriche **per settore** (REIT, BDC, Tech, Energy, …) e produce verdetto locale (compra/attenzione/evita) + report testuale.

Guida operativa: [`GUIDA.md`](GUIDA.md).

## Stack

- Python 3, Flask (`app.py` → porta **5055**)
- `yfinance` per dati Yahoo automatici
- Parser HTML locale (BeautifulSoup) per Investing/TIKR/Finviz/…
- Nessun database — output in `output/`

## Flusso dati

```text
Ticker (es. GOOGL, BRK-B, SAP.DE)
        │
yahoo_api.fetch_yahoo_metrics     → prezzo, P/E, EPS, FCF, growth, D/E, …
        │
HTML upload (browser o CLI)
  ├── TIKR bundle (consigliato: tutte le tab insieme)
  ├── Investing overview (obbligatorio in UI)
  └── Opzionali: Finviz, MarketWatch, GuruFocus, TipRanks, Morningstar
        │
tikr_bundle.py / classify_html    → smista tab per URL
        │
scoring_engine.run_analysis       → score settoriale + verdetto
        │
output/report_<settore>_<timestamp>.txt
```

**Priorità estrazione:** TIKR (tutte le tab) → Investing → fonti extra. Yahoo vince sui campi che fornisce.

## Settori supportati

| Settore | Metriche chiave |
|---------|------------------|
| REIT | FFO/AFFO, NAV, Debt/EBITDA, SS NOI |
| BDC | NII, NAV, non-accrual, coverage |
| FINANCIALS | CET1, ROE/ROA, NIM, NPL |
| TECH | Growth, Rule of 40, NRR, margini |
| ENERGY | EV/EBITDA, FCF yield, payout |
| HEALTHCARE | Gross margin, R&D/Rev, pipeline |
| CONSUMER | Same-store, inventory, FCF conversion |
| INDUSTRIAL | Book-to-bill, ROIC, capex |
| GENERICO | P/E, EPS, FCF, D/E standard |

Alias: `BANCA` → FINANCIALS, `UTILITIES` → ENERGY.

## Struttura cartelle

```
stock_analysis/
├── app.py                 # Flask UI + API JSON
├── analizza_azione.py     # CLI analisi
├── scoring_engine.py      # Motore score + verdetto
├── yahoo_api.py           # Wrapper yfinance
├── tikr_bundle.py         # Dump multi-file TIKR
├── smart_money.py         # Bonus 13F Dataroma (+0…+3)
├── sectors.py             # Definizioni settore
├── templates/index.html
├── static/app.js + style.css
├── input/                 # HTML opzionali
├── output/                # Report .txt + _screen_rank.json
├── GUIDA.md
└── avvia_web.bat
```

## Superinvestors (Dataroma 13F)

Bonus di **conferma** (+0…+3), mai segnale standalone:
- Tier 1 (Buffett, Pabrai…): fino +3
- Vendite massive: fino −2
- Dati in ritardo ~45 giorni; titoli non-US spesso assenti

## Affidabilità minima

Servono ≥ **5/7** campi critici Yahoo: `price, pe, eps, market_cap, rev_growth, fcf, de`.  
Metriche settoriali (FFO, CET1…) spesso solo da TIKR.

## Comandi

```powershell
.\avvia_web.bat                    # http://127.0.0.1:5055
python analizza_azione.py GOOGL
python tikr_bundle.py --overview "...\TIKR.html" --ticker CSAN --sector ENERGY
```

## Non in scope

- Trading automatico o alert tempo reale
- API TIKR/Investing ufficiali (solo HTML salvato dall’utente)
- Portafoglio multi-ticker persistente

## Auto-analisi + portafoglio + Telegram (2026-09)

| Modulo | Ruolo |
|--------|--------|
| `auto_analyze.py` | Scoring solo Yahoo — niente HTML |
| `portfolio_db.py` | SQLite multi-ticker + storico score |
| `telegram_notify.py` | Alert Telegram su variazione score |

API Flask: `/api/auto-analyze/<ticker>`, `/api/portfolio`, `/api/portfolio/scan`

```powershell
python auto_analyze.py NVDA --add
python auto_analyze.py --scan
```
