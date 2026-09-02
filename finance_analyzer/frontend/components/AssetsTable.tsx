"use client";

import { useEffect, useRef } from "react";
import CopyableTicker, { tickerForCopy } from "@/components/CopyableTicker";
import AnalystDateLine from "@/components/AnalystDateLine";
import type { AssetRow } from "@/lib/api";
import {
  fmtPct,
  fmtPrice,
  fmtBuyability,
  fmtAnalystTargetRange,
  fmtSpreadPct,
  typeLabel,
  colorClass,
  buyabilityClass,
  spreadQualityClass,
  analystCountClass,
} from "@/lib/format";

interface Props {
  assets: AssetRow[];
  selectedId: string | null;
  loading?: boolean;
  pageKey?: string;
  onSelect: (id: string) => void;
  onDetail: (id: string) => void;
}

const COL_COUNT = 13;

export default function AssetsTable({
  assets,
  selectedId,
  loading,
  pageKey,
  onSelect,
  onDetail,
}: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const tableWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const viewport = viewportRef.current;
    const track = trackRef.current;
    const tableWrap = tableWrapRef.current;
    if (!viewport || !track || !tableWrap) return;

    const trackInner = track.querySelector<HTMLElement>(".table-scroll-track-inner");
    if (!trackInner) return;

    const syncTrackWidth = () => {
      trackInner.style.width = `${tableWrap.scrollWidth}px`;
    };

    syncTrackWidth();
    const resizeObserver = new ResizeObserver(syncTrackWidth);
    resizeObserver.observe(tableWrap);

    let syncing = false;
    const syncViewportToTrack = () => {
      if (syncing) return;
      syncing = true;
      track.scrollLeft = viewport.scrollLeft;
      syncing = false;
    };
    const syncTrackToViewport = () => {
      if (syncing) return;
      syncing = true;
      viewport.scrollLeft = track.scrollLeft;
      syncing = false;
    };

    viewport.addEventListener("scroll", syncViewportToTrack);
    track.addEventListener("scroll", syncTrackToViewport);

    return () => {
      resizeObserver.disconnect();
      viewport.removeEventListener("scroll", syncViewportToTrack);
      track.removeEventListener("scroll", syncTrackToViewport);
    };
  }, [assets, loading, pageKey]);

  return (
    <div className="table-scroll-panel">
      <div
        ref={viewportRef}
        className="table-scroll-viewport"
        tabIndex={0}
        role="region"
        aria-label="Tabella titoli"
      >
        <div
          ref={tableWrapRef}
          className={`table-wrap${loading ? " table-loading" : ""}`}
          key={pageKey}
        >
          {loading && (
            <div className="table-loading-overlay">
              <div className="spinner spinner-sm" />
              <span>Caricamento pagina…</span>
            </div>
          )}
          <table className="assets-table">
            <thead>
              <tr>
                <th className="col-detail" aria-label="Dettaglio" />
                <th className="col-name">Nome</th>
                <th className="col-country">Paese</th>
                <th className="col-type">Tipo</th>
                <th className="col-num" title="CAGR storico (solo ETF)">
                  Rend. ann. storico
                </th>
                <th className="col-num">YTD</th>
                <th className="col-buy">% Buy</th>
                <th className="col-num">Range tgt</th>
                <th className="col-num col-spread">Spread</th>
                <th className="col-num">Prezzo</th>
                <th className="col-num">Atteso</th>
                <th className="col-num">Prev. 12m</th>
                <th className="col-num">Range sim.</th>
              </tr>
            </thead>
            <tbody>
              {!loading && assets.length === 0 && (
                <tr>
                  <td colSpan={COL_COUNT} className="empty-row">
                    Nessun titolo in questa pagina (prova altri filtri).
                  </td>
                </tr>
              )}
              {assets.map((a) => (
                <tr
                  key={a.id}
                  className={selectedId === a.id ? "selected" : ""}
                  onClick={() => onSelect(a.id)}
                >
                  <td className="col-detail">
                    <button
                      type="button"
                      className="detail-btn"
                      title="Dettaglio e grafico 20 giorni"
                      aria-label={`Dettaglio ${a.name}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onDetail(a.id);
                      }}
                    >
                      🔍
                    </button>
                  </td>
                  <td>
                    <CopyableTicker
                      name={a.name}
                      ticker={tickerForCopy(a)}
                      subtitle={
                        a.stooq_symbol
                          ? `${a.stooq_symbol}${a.price_source ? ` · ${a.price_source}` : ""}`
                          : undefined
                      }
                      stopPropagation
                    />
                  </td>
                  <td className="country-cell">{a.country}</td>
                  <td>
                    <span className={`badge badge-${a.type}`}>{typeLabel(a.type)}</span>
                  </td>
                  <td className={colorClass(a.rendimento_annuo_pct)}>
                    {a.type === "etf" ? fmtPct(a.rendimento_annuo_pct) : "—"}
                  </td>
                  <td className={colorClass(a.ytd_pct)}>{fmtPct(a.ytd_pct)}</td>
                  <td>
                    <span className={`buyability ${buyabilityClass(a.buyability_pct)}`}>
                      {fmtBuyability(a.buyability_pct)}
                    </span>
                    {a.analyst_count > 0 && (
                      <span className={`analyst-count ${analystCountClass(a.analyst_count)}`}>
                        · {a.analyst_count} anal.
                      </span>
                    )}
                    <span className="analyst-hint analyst-hint-compact" title={a.analyst_label}>
                      {a.analyst_label}
                    </span>
                    <AnalystDateLine
                      consensusDate={a.analyst_consensus_date}
                      lastTargetDate={a.analyst_last_target_date}
                      lastRatingDate={a.analyst_last_rating_date}
                      lastFirm={a.analyst_last_firm}
                    />
                  </td>
                  <td className="range analyst-range">
                    {fmtAnalystTargetRange(a.analyst_target_low, a.analyst_target_high)}
                  </td>
                  <td>
                    <span
                      className={`spread-badge ${spreadQualityClass(a.analyst_target_spread_pct)}`}
                      title="Spread tra target min e max analisti"
                    >
                      {fmtSpreadPct(a.analyst_target_spread_pct)}
                    </span>
                  </td>
                  <td>{fmtPrice(a.current_price)}</td>
                  <td className={colorClass(a.analyst_upside_pct)}>
                    {fmtPrice(a.valore_atteso)}
                    {a.analyst_upside_pct != null && (
                      <span className="forecast-ret"> ({fmtPct(a.analyst_upside_pct)} upside)</span>
                    )}
                  </td>
                  <td className={colorClass(a.previsione_rendimento_pct)}>
                    {a.previsione_rendimento_pct != null
                      ? fmtPct(a.previsione_rendimento_pct)
                      : "—"}
                    {a.previsione_prezzo != null && (
                      <span className="forecast-ret"> → {fmtPrice(a.previsione_prezzo)}</span>
                    )}
                  </td>
                  <td className="range">
                    {a.previsione_range_basso != null && a.previsione_range_alto != null
                      ? `${fmtPrice(a.previsione_range_basso)} – ${fmtPrice(a.previsione_range_alto)}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="table-scroll-footer">
        <div
          ref={trackRef}
          className="table-scroll-track"
          tabIndex={-1}
          aria-hidden="true"
        >
          <div className="table-scroll-track-inner" />
        </div>
        <div className="table-scroll-hint">
          ↔ Scorri orizzontalmente per vedere tutte le colonne
        </div>
      </div>
    </div>
  );
}
