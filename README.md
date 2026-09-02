# Final Finance — Quant Platform Unificata

Alert Telegram intraday + scoring fondamentale + analisi quantitativa + regolatori internazionali.

**Documentazione completa:** [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) (architettura, filtri, score, deploy, debug).

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env    # TELEGRAM + FINNHUB

python -m finance_alert --status
python -m finance_alert --dry-run
python -m finance_alert --analyze NVDA
```

Moduli inclusi: `finance_alert/` · `stock_analysis/` · `finance_analyzer/`

---

# finance-notify (legacy name)

Alert Telegram su **eventi di borsa verificabili** (utili, surprise EPS, gap pre/after-hours, peer in ritardo, 8-K).  
Job periodico + bot Telegram. **Non è una previsione certa del +7%** prima che succeda.

Esempio NVIDIA: l’alert utile è «utili fuori / EPS sopra stime → possibile gap» oppure «NVDA +5% dalla chiusura», non indovinare il +7% in anticipo.

## Modalità ANTICIPO (attiva ora)

Obiettivo: segnali **prima** o **all’inizio** di un possibile salto, non “è già +7% in seduta”.

| Priorità | Segnale | Anticipo reale |
|----------|---------|----------------|
| 1 | **Utili in arrivo** (`earnings_soon`) | Ore prima — setup volatilità, **non** direzione |
| 2 | **Surprise EPS / ricavi** | Minuti dopo i numeri (spesso AMC) — finestra gap |
| 3 | **8-K Item 2.02** | Ufficiale SEC, spesso insieme al primo movimento AH |
| 4 | **Gap precoce pre/AH** (≥1.5%) | Prima dell’open USA |
| 5 | **Peer ancora fermi** | NVDA già su, AMD no → catch-up possibile |
| 6 | **Catalizzatore wire** | Guidance/M&A/FDA (non editoriali) |

Spenti di proposito: spike in seduta e momentum (“già salito”).

**Limite onesto:** nessuno (gratis) ti dice il +7% *prima* della notizia. Il massimo realistico è: setup utili → numeri fuori → gap AH/pre → peer in ritardo.

## Fonti: registrazione sì / no

**Nessuno scraping HTML.** Solo API JSON o RSS.

### Consigliato — registrati (gratis)

| Fonte | Serve account? | A cosa serve | Link |
|-------|----------------|--------------|------|
| **Finnhub** | Sì, API key free | Quote, calendario earnings, news | [finnhub.io/register](https://finnhub.io/register) |
| **Telegram bot** | Già ce l’hai | Invio messaggi | stesso `TELEGRAM_BOT_TOKEN` / `CHAT_ID` di calcio/recensioni |

Hai già Finnhub (e FMP / Twelve Data) nel `.env` di `Finance-Analyzer-main`: in locale questo progetto **li legge da solo**.

### Opzionale

| Fonte | Serve account? | Note |
|-------|----------------|------|
| **FMP** | Sì, free 250 req/giorno | Fallback earnings + news USA | [developer docs](https://site.financialmodelingprep.com/developer/docs) |
| **Twelve Data** | Sì, free 800 req/giorno | Fallback prezzi | [twelvedata.com/register](https://twelvedata.com/register) |
| **Polygon** | Sì, piano free limitato | Quote + news più “pro” | [polygon.io](https://polygon.io/dashboard/signup) |
| **Alpha Vantage** | Sì | Non usato di default (25 req/giorno) | — |

### Senza registrazione (funzionano comunque)

| Fonte | API key? | Note |
|-------|----------|------|
| **Yahoo chart** `query1.finance.yahoo.com` | No | Prezzi e barre 5 min. **Non ufficiale**, può dare 429 o rompersi. ToS Yahoo: uso personale, non scraping aggressivo. |
| **Yahoo RSS** | No | Fallback notizie per ticker |
| **SEC EDGAR** `data.sec.gov` | No | 8-K ufficiali. Serve solo un’email nel User-Agent (`SEC_CONTACT_EMAIL`) |

Per GitHub Actions copia le stesse chiavi come **secrets** del repo (`FINNHUB_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, opzionali FMP/Twelve/Polygon/`SEC_CONTACT_EMAIL`).

## Avvio locale

```powershell
cd C:\Users\valba\Desktop\corsi\finance-alert
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Opzionale: copia `.env.example` → `.env`. Se non lo fai, usa i `.env` dei progetti accanto.

```powershell
python -m finance_alert --status     # quali fonti sono vive
python -m finance_alert --dry-run    # calcola, non invia
python -m finance_alert --test       # ping sul bot
python -m finance_alert              # scan + invio nuovi alert
streamlit run app.py                 # cruscotto
```

Watchlist e soglie: `config/watchlist.yaml`.

## Automatico (PC spento)

1. Secrets GitHub (Settings → Secrets and variables → Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `FINNHUB_API_KEY`
   - **consigliato:** `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` (dedupe tra run CI)
   - opzionali: `FMP_API_KEY`, `TWELVE_DATA_API_KEY`, `POLYGON_API_KEY`, `NEWSAPI_API_KEY`, `MARKETAUX_API_TOKEN`, `BENZINGA_API_TOKEN`, `GEMINI_API_KEY`, `NEWS_LLM_PROVIDER`, `SEC_CONTACT_EMAIL`, `FCA_*`, `FSA_EDINET_API_KEY`

**Upstash Redis (dedupe):** [console.upstash.com](https://console.upstash.com) → Create database → tab REST → copia URL e token nei secrets. Senza Upstash, la dedupe usa solo cache file locale (ogni run GitHub Actions parte da zero).

2. Workflow `Telegram borsa alerts`: ogni **20 min** pre-market → after-hours USA (08–23 UTC, lun–ven), ogni **10 min** all’open USA, + digest pre-open
3. Dopo il primo push: Actions → workflow → **Run workflow** (test = true) per verificare Telegram

Cron locale (alternativa):

```powershell
# ogni 15 min, solo se Python è nel PATH
python -m finance_alert
```

## Limiti onesti

- Piani free: ritardi, rate limit, pochi ticker (qui 10 di default).
- GitHub Actions può ritardare i cron di alcuni minuti.
- Yahoo è un fallback, non una fonte da contratto.
- Nessun modello predice in modo affidabile il salto pre-earnings: qui si combinano **notizia ufficiale + surprise + prezzo**.
