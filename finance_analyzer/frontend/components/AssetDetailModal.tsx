"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { AssetRow, RecentBarsResponse } from "@/lib/api";
import AnalystDateLine from "@/components/AnalystDateLine";
import ExternalResearchLinks from "@/components/ExternalResearchLinks";
import InvestingGlossary from "@/components/InvestingGlossary";
import { tickerForCopy } from "@/components/CopyableTicker";
import {
  fmtPct,
  fmtPrice,
  fmtBuyability,
  typeLabel,
  colorClass,
  buyabilityClass,
} from "@/lib/format";

interface Props {
  asset: AssetRow | null;
  recent: RecentBarsResponse | null;
  loading: boolean;
  onClose: () => void;
}

export default function AssetDetailModal({ asset, recent, loading, onClose }: Props) {
  if (!asset) return null;

  const ticker = tickerForCopy(asset);

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        className="modal-card"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
      >
        <div className="modal-header">
          <div>
            <h2 id="detail-title">{asset.name}</h2>
            <p className="modal-sub">
              <code className="modal-ticker-code">{ticker}</code>
              {" · "}
              {asset.stooq_symbol} · {asset.country} ·{" "}
              <span className={`badge badge-${asset.type}`}>{typeLabel(asset.type)}</span>
            </p>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Chiudi">
            ×
          </button>
        </div>

        <ExternalResearchLinks ticker={ticker} />

        <div className="modal-metrics">
          <div>
            <span className="metric-label">Prezzo</span>
            <span className="metric-value">{fmtPrice(asset.current_price)}</span>
          </div>
          <div>
            <span className="metric-label">% Buy (analisti)</span>
            <span className={`metric-value ${buyabilityClass(asset.buyability_pct)}`}>
              {fmtBuyability(asset.buyability_pct)}
            </span>
            <AnalystDateLine
              consensusDate={asset.analyst_consensus_date}
              lastTargetDate={asset.analyst_last_target_date}
              lastRatingDate={asset.analyst_last_rating_date}
              lastFirm={asset.analyst_last_firm}
              className="analyst-date modal-analyst-date"
            />
          </div>
          <div>
            <span className="metric-label">Previsione 12m</span>
            <span className={`metric-value ${colorClass(asset.previsione_rendimento_pct)}`}>
              {fmtPct(asset.previsione_rendimento_pct)}
            </span>
          </div>
          <div>
            <span className="metric-label">YTD</span>
            <span className={`metric-value ${colorClass(asset.ytd_pct)}`}>
              {fmtPct(asset.ytd_pct)}
            </span>
          </div>
        </div>

        <div className="modal-chart">
          <h3>Ultimi 20 giorni ({recent?.source ?? "Stooq/Yahoo/Finnhub"})</h3>
          {loading && <p className="modal-loading">Caricamento dati…</p>}
          {!loading && recent && recent.bars.length > 0 && (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={recent.bars}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 10 }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{
                    background: "#1e293b",
                    border: "1px solid #334155",
                    borderRadius: 8,
                  }}
                />
                <Line type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot />
              </LineChart>
            </ResponsiveContainer>
          )}
          {!loading && (!recent || recent.bars.length === 0) && (
            <p className="modal-loading">Dati non disponibili per questo titolo.</p>
          )}
        </div>

        <p className="analyst-hint">{asset.analyst_label}</p>

        <InvestingGlossary />
      </div>
    </div>
  );
}
