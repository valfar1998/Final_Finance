"use client";

import { useCallback, useState } from "react";

interface Props {
  name: string;
  /** Ticker copiato (es. AAPL, ENEL.MI) */
  ticker: string;
  /** Sottotitolo opzionale (es. stooq symbol) */
  subtitle?: string;
  className?: string;
  /** Evita propagazione click (righe tabella / card startup) */
  stopPropagation?: boolean;
}

export default function CopyableTicker({
  name,
  ticker,
  subtitle,
  className = "",
  stopPropagation = false,
}: Props) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(
    async (e: React.SyntheticEvent) => {
      if (stopPropagation) e.stopPropagation();
      try {
        await navigator.clipboard.writeText(ticker);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      } catch {
        /* fallback silenzioso */
      }
    },
    [ticker, stopPropagation],
  );

  const onCopyKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        void copy(e);
      }
    },
    [copy],
  );

  return (
    <div className={`copyable-ticker ${className}`.trim()}>
      <strong className="copyable-ticker-name" title={name}>
        {name}
      </strong>
      <span className="copyable-ticker-row">
        <code className="copyable-ticker-code" title={`Ticker: ${ticker}`}>
          {ticker}
        </code> 
        <span
          role="button"
          tabIndex={0}
          className={`copy-ticker-btn${copied ? " copied" : ""}`}
          title={copied ? "Copiato!" : `Copia ticker ${ticker}`}
          aria-label={copied ? "Ticker copiato" : `Copia ticker ${ticker}`}
          onClick={copy}
          onKeyDown={onCopyKeyDown}
        >
          {copied ? "✓" : "⎘"}
        </span>
        {subtitle && <span className="copyable-ticker-sub">{subtitle}</span>}
      </span>
    </div>
  );
}

export function tickerForCopy(row: {
  yf_ticker?: string;
  symbol?: string;
  stooq_symbol?: string;
}): string {
  if (row.yf_ticker) return row.yf_ticker;
  if (row.symbol) return row.symbol;
  if (row.stooq_symbol) {
    const base = row.stooq_symbol.split(".")[0];
    return base.toUpperCase();
  }
  return "—";
}
