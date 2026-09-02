# Stock Analysis — Yahoo API + HTML

Yahoo Finance arriva **in automatico** (`yfinance`): basta il ticker.
Investing, TIKR e altre fonti restano HTML SingleFile.

## Flusso

1. Avvia `avvia_web.bat` → `http://127.0.0.1:5055`
2. Inserisci ticker (es. `GOOGL`, `BRK-B`, `SAP.DE`)
3. Scegli il **settore** (attiva le metriche giuste)
4. Carica Investing.com overview (obbligatorio)
5. TIKR — **dump unico** (consigliato): trascina tutti gli HTML SingleFile insieme.
   Lo script legge l’URL salvato (`/stock/about`, `financials?tab=cf`, `multiples`…) e smista le tab da solo.
   In alternativa: 10 box manuali per tab, oppure da terminale:

   ```
   python tikr_bundle.py --overview "C:\Users\...\TIKR Terminal (...).html" --ticker CSAN --sector ENERGY
   ```

   Partendo dall’Overview cerca i gemelli **nella stessa cartella** (Downloads, ecc.).
6. Opzionali: Finviz, MarketWatch, GuruFocus, TipRanks, Morningstar
7. Avvia scoring

Priorità estrazione HTML: **TIKR (tutte le tab unite) → Investing → fonti extra**. Yahoo API vince sempre sui campi che fornisce.

## Settori

| Settore | Metriche chiave |
|---------|-----------------|
| REIT | FFO/AFFO, NAV, Debt/EBITDA, SS NOI, yield su FFO |
| BDC | NII, NAV, non-accrual, coverage, D/E regolamentare |
| FINANCIALS | CET1, ROE/ROA, NIM, Cost/Income, NPL |
| TECH | Growth, gross/FCF margin, R&D, Rule of 40, NRR |
| ENERGY | EV/EBITDA, Debt/EBITDA, FCF yield, payout |
| HEALTHCARE | Gross margin, R&D/Rev, pipeline/patent risk |
| CONSUMER | Same-store sales, margini, inventory, FCF conversion |
| INDUSTRIAL | Book-to-bill, ROIC, EBITDA margin, capex |
| COMMUNICATION | ARPU/churn, EBITDA, capex, FCF post-capex |
| GENERICO | P/E, EPS, FCF, D/E, growth standard |

Alias: `BANCA` → FINANCIALS, `UTILITIES` → ENERGY.

## Superinvestors 13F (Dataroma)

Bonus di **conferma** (+0…+3), non segnale di acquisto:
- Tier 1 (Buffett, Pabrai, Li Lu…): fino a +3
- Tier 2 (Druckenmiller, Klarman…): fino a +2
- Tier 3 (attivisti): fino a +1
- Vendite massicce dei grandi: fino a −2
- **Mai** se il modello dice già EVITA / dati insufficienti
- 13F in ritardo ~45 giorni; titoli non-US spesso assenti su Dataroma

## Affidabilità

Servono almeno **5/7** campi critici Yahoo: `price, pe, eps, market_cap, rev_growth, fcf, de`.
Metriche settoriali (FFO, CET1…) spesso solo da TIKR: senza di esse lo scoring usa fallback più deboli.
