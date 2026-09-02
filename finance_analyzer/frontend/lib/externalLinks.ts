/**
 * Link esterni per ricerca manuale (SEC, Yahoo, TIKR).
 * TIKR non espone URL pubblici per ticker — apre l'app; l'utente cerca il simbolo.
 */

export function usSymbol(ticker: string): string {
  return ticker.split(".")[0].toUpperCase().trim();
}

export function yahooFinanceUrl(ticker: string): string {
  return `https://finance.yahoo.com/quote/${encodeURIComponent(ticker.toUpperCase())}/`;
}

/** Filings e documenti ufficiali SEC (ricerca per ticker USA). */
export function secEdgarUrl(ticker: string): string {
  const sym = usSymbol(ticker);
  return `https://www.sec.gov/edgar/search/#/q=${encodeURIComponent(sym)}&dateRange=custom&category=custom&forms=10-K,10-Q,8-K,DEF%2014A,S-1,S-3`;
}

/** TIKR Terminal — ricerca manuale del ticker nell'app. */
export function tikrAppUrl(ticker: string): string {
  const sym = usSymbol(ticker);
  return `https://app.tikr.com/?utm_source=finance-analyzer&ticker=${encodeURIComponent(sym)}`;
}

export interface ExternalLinkItem {
  id: string;
  label: string;
  href: string;
  hint: string;
}

export function researchLinksForTicker(ticker: string): ExternalLinkItem[] {
  const sym = usSymbol(ticker);
  return [
    {
      id: "yahoo",
      label: "Yahoo Finance",
      href: yahooFinanceUrl(ticker),
      hint: `Grafico, analisti, target per ${ticker}`,
    },
    {
      id: "sec",
      label: "SEC EDGAR",
      href: secEdgarUrl(ticker),
      hint: `10-K, 10-Q, 8-K ufficiali per ${sym} (USA)`,
    },
    {
      id: "tikr",
      label: "TIKR",
      href: tikrAppUrl(ticker),
      hint: `Apri TIKR e cerca «${sym}» (Financials, Estimates, Filings)`,
    },
  ];
}

/** Guida locale (statica in /public). */
export const GUIDA_TIKR_PATH = "/guida-tikr/GUIDA_LETTURA_TIKR_ADGM.md";
