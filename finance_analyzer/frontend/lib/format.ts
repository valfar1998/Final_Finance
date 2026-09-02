export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}%`;
}

export function fmtPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtBuyability(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "N/D";
  return `${v.toFixed(1)}%`;
}

export function typeLabel(type: string): string {
  switch (type) {
    case "etf":
      return "ETF";
    default:
      return "Azione";
  }
}

export function colorClass(v: number | null | undefined): string {
  if (v == null) return "";
  if (v > 0) return "positive";
  if (v < 0) return "negative";
  return "";
}

export function fmtTargetRange(
  low: number | null | undefined,
  high: number | null | undefined,
  spreadPct?: number | null,
): string {
  if (low == null || high == null) return "—";
  const spread =
    spreadPct != null && !Number.isNaN(spreadPct) ? ` · spread ${spreadPct.toFixed(0)}%` : "";
  return `${fmtPrice(low)} – ${fmtPrice(high)}${spread}`;
}

/** Solo min–max target analisti (colonna tabella). */
export function fmtAnalystTargetRange(
  low: number | null | undefined,
  high: number | null | undefined,
): string {
  if (low == null || high == null) return "—";
  return `${fmtPrice(low)} – ${fmtPrice(high)}`;
}

export function fmtSpreadPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v.toFixed(0)}%`;
}

/** Verde = consenso stretto, rosso = disaccordo alto. */
export function spreadQualityClass(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "";
  if (v <= 40) return "positive";
  if (v <= 60) return "neutral";
  return "negative";
}

export function analystCountClass(n: number | null | undefined): string {
  if (n == null || n <= 0) return "";
  if (n >= 10) return "positive";
  if (n >= 5) return "neutral";
  return "negative";
}

export function buyabilityClass(v: number | null | undefined): string {
  if (v == null) return "neutral";
  if (v >= 65) return "positive";
  if (v <= 35) return "negative";
  return "neutral";
}

export function fmtDateIt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.slice(0, 10);
  const [y, m, day] = d.split("-");
  if (!y || !m || !day) return iso;
  return `${day}/${m}/${y}`;
}

export function daysSinceDate(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = new Date(iso.slice(0, 10));
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}

export function analystDateIsStale(iso: string | null | undefined, maxDays = 120): boolean {
  const days = daysSinceDate(iso);
  return days != null && days > maxDays;
}

export function fmtAnalystDates(row: {
  analyst_consensus_date?: string | null;
  analyst_last_target_date?: string | null;
  analyst_last_rating_date?: string | null;
  analyst_last_firm?: string | null;
}): string | null {
  const parts: string[] = [];
  if (row.analyst_last_target_date) {
    let s = `Target ${fmtDateIt(row.analyst_last_target_date)}`;
    if (row.analyst_last_firm) s += ` (${row.analyst_last_firm})`;
    parts.push(s);
  } else if (row.analyst_last_rating_date) {
    let s = `Rating ${fmtDateIt(row.analyst_last_rating_date)}`;
    if (row.analyst_last_firm) s += ` (${row.analyst_last_firm})`;
    parts.push(s);
  }
  if (row.analyst_consensus_date) {
    parts.push(`Consenso ${fmtDateIt(row.analyst_consensus_date)}`);
  }
  return parts.length ? parts.join(" · ") : null;
}
