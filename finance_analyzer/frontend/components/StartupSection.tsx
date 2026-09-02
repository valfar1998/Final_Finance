"use client";

import { useEffect, useState } from "react";
import CopyableTicker, { tickerForCopy } from "@/components/CopyableTicker";
import AnalystDateLine from "@/components/AnalystDateLine";
import { fetchStartups, type AssetRow } from "@/lib/api";
import {
  fmtPct,
  fmtPrice,
  fmtBuyability,
  fmtTargetRange,
  colorClass,
  buyabilityClass,
} from "@/lib/format";

export const MIN_ANALYSTS_OPTIONS = [
  { value: 0, label: "Nessun minimo" },
  { value: 3, label: "≥ 3 analisti" },
  { value: 5, label: "≥ 5 analisti (consigliato)" },
  { value: 10, label: "≥ 10 analisti" },
  { value: 15, label: "≥ 15 analisti" },
];

/** Max spread % tra target min e max (0 = nessun limite) */
export const MAX_SPREAD_OPTIONS = [
  { value: 0, label: "Spread: nessun limite" },
  { value: 20, label: "Spread ≤ 20% (forte consenso)" },
  { value: 40, label: "Spread ≤ 40% (consigliato)" },
  { value: 60, label: "Spread ≤ 60%" },
  { value: 80, label: "Spread ≤ 80%" },
];

interface Props {
  region: string;
  onSelect: (id: string) => void;
}

export default function StartupSection({ region, onSelect }: Props) {
  const [startups, setStartups] = useState<AssetRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [minAnalysts, setMinAnalysts] = useState(5);
  const [maxSpread, setMaxSpread] = useState(40);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchStartups({
      region,
      min_analysts: minAnalysts,
      max_target_spread_pct: maxSpread,
    })
      .then((data) => {
        if (!cancelled) setStartups(data.startups ?? []);
      })
      .catch(() => {
        if (!cancelled) setStartups([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [region, minAnalysts, maxSpread]);

  return (
    <section className="startup-section">
      <h2 className="section-title">Start-up / titoli economici consigliati</h2>
      <p className="section-desc">
        Azioni a prezzo contenuto con consenso analisti positivo. Usa i filtri per escludere
        titoli con pochi analisti o range target troppo ampio (disaccordo). Non è consulenza
        finanziaria.
      </p>

      <div className="startup-filters">
        <label className="filter-field">
          <span>Min. analisti</span>
          <select
            value={minAnalysts}
            onChange={(e) => setMinAnalysts(Number(e.target.value))}
          >
            {MIN_ANALYSTS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>Range target (spread)</span>
          <select value={maxSpread} onChange={(e) => setMaxSpread(Number(e.target.value))}>
            {MAX_SPREAD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {!loading && (
          <span className="startup-filter-count">
            <strong>{startups.length}</strong> titoli
          </span>
        )}
      </div>

      <p className="section-desc startup-range-hint">
        Il <strong>range</strong> (es. 42–76) è in <strong>prezzo</strong> ($/€), non una scala
        1–100: min e max target degli analisti. Lo <strong>spread</strong> misura quanto
        discordano: ≤40% è buono, &gt;60% = alto disaccordo. Con 1 solo analista (10–10) lo
        spread è 0% ma il dato è poco affidabile — usa ≥5 analisti.
      </p>

      {loading && (
        <div className="startup-loading">
          <div className="spinner spinner-sm" />
          <span>Caricamento titoli consigliati…</span>
        </div>
      )}

      {!loading && !startups.length && (
        <p className="section-desc muted">
          Nessun titolo con questi filtri. Prova ad allargare spread o abbassare il minimo
          analisti, oppure naviga le pagine USA per popolare la cache.
        </p>
      )}

      {!loading && startups.length > 0 && (
        <div className="startup-grid">
          {startups.map((s) => (
            <div
              key={s.id}
              role="button"
              tabIndex={0}
              className="startup-card"
              onClick={() => onSelect(s.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(s.id);
                }
              }}
            >
              <div className="startup-card-header">
                <CopyableTicker
                  name={s.name}
                  ticker={tickerForCopy(s)}
                  stopPropagation
                />
                <span className="startup-country">{s.country}</span>
              </div>
              <div className="startup-metrics">
                <div>
                  <span className="metric-label">Prezzo</span>
                  <span className="metric-value">{fmtPrice(s.current_price)}</span>
                </div>
                <div>
                  <span className="metric-label">% Buy</span>
                  <span className={`metric-value ${buyabilityClass(s.buyability_pct)}`}>
                    {fmtBuyability(s.buyability_pct)}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Analisti</span>
                  <span className="metric-value">{s.analyst_count || "—"}</span>
                </div>
                <div>
                  <span className="metric-label">Range target</span>
                  <span className="metric-value">
                    {fmtTargetRange(
                      s.analyst_target_low,
                      s.analyst_target_high,
                      s.analyst_target_spread_pct,
                    )}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Target medio</span>
                  <span className={`metric-value ${colorClass(s.analyst_upside_pct)}`}>
                    {fmtPrice(s.analyst_target_mean)}
                    {s.analyst_upside_pct != null && (
                      <small> ({fmtPct(s.analyst_upside_pct)})</small>
                    )}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Valore atteso</span>
                  <span className="metric-value">{fmtPrice(s.valore_atteso)}</span>
                </div>
              </div>
              <p className="startup-hint">{s.analyst_label}</p>
              <AnalystDateLine
                consensusDate={s.analyst_consensus_date}
                lastTargetDate={s.analyst_last_target_date}
                lastRatingDate={s.analyst_last_rating_date}
                lastFirm={s.analyst_last_firm}
                className="startup-analyst-date"
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
