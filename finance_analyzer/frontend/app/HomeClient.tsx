"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AssetDetailModal from "@/components/AssetDetailModal";
import AssetsTable from "@/components/AssetsTable";
import AnalystQualityGuide from "@/components/AnalystQualityGuide";
import ComparisonChart from "@/components/ComparisonChart";
import FilterBar from "@/components/FilterBar";
import Pagination from "@/components/Pagination";
import PriceChart from "@/components/PriceChart";
import StartupSection from "@/components/StartupSection";
import {
  fetchAsset,
  fetchAssetRecent,
  fetchDashboard,
  fetchUniverseStats,
  type AssetRow,
  type RecentBarsResponse,
  type UniverseStats,
} from "@/lib/api";
import { DEFAULT_FILTERS, type FilterState } from "@/lib/filters";

const CHART_COLORS: Record<string, string> = {
  azione: "#3b82f6",
  etf: "#22c55e",
};

function LoadingShell() {
  return (
    <div className="app">
      <div className="loading">
        <div className="spinner" />
        <p>Caricamento universo azionario (migliaia di titoli)…</p>
        <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
          La prima pagina può richiedere 30–60 secondi. Poi i dati vengono messi in cache.
        </p>
      </div>
    </div>
  );
}

export default function HomeClient() {
  const [assets, setAssets] = useState<AssetRow[]>([]);
  const [errors, setErrors] = useState<{ id: string; name: string; error: string }[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedChart, setSelectedChart] = useState<AssetRow | null>(null);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [universeStats, setUniverseStats] = useState<UniverseStats | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [detailAsset, setDetailAsset] = useState<AssetRow | null>(null);
  const [detailRecent, setDetailRecent] = useState<RecentBarsResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [chartLoading, setChartLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tableRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);

  // Table: reload on page / pageSize / filters
  useEffect(() => {
    const requestId = ++requestIdRef.current;
    setTableLoading(true);
    setError(null);
    setAssets([]);

    (async () => {
      try {
        const [data, stats] = await Promise.all([
          fetchDashboard({
            page,
            page_size: pageSize,
            region: filters.region,
            type: filters.type,
            sort: filters.sort,
            min_buyability: filters.minBuyability,
            min_previsione_pct: filters.minPrevisionePct,
            q: filters.search,
          }),
          fetchUniverseStats().catch(() => null),
        ]);

        if (requestId !== requestIdRef.current) return;

        setAssets(data.assets);
        setErrors(data.errors);
        setTotal(data.total ?? data.count);
        setTotalPages(data.total_pages ?? 1);
        if (stats) setUniverseStats(stats);
      } catch (e) {
        if (requestId !== requestIdRef.current) return;
        setError(e instanceof Error ? e.message : "Errore sconosciuto");
      } finally {
        if (requestId === requestIdRef.current) {
          setTableLoading(false);
          setInitialLoading(false);
        }
      }
    })();
  }, [
    page,
    pageSize,
    filters.region,
    filters.type,
    filters.sort,
    filters.minBuyability,
    filters.minPrevisionePct,
    filters.search,
  ]);

  const chartSample = useMemo(() => assets.slice(0, 10), [assets]);

  const handleSelect = useCallback(async (id: string) => {
    setSelectedId(id);
    setChartLoading(true);
    try {
      const full = await fetchAsset(id);
      setSelectedChart(full);
    } catch {
      const row = assets.find((a) => a.id === id);
      setSelectedChart(row ?? null);
    } finally {
      setChartLoading(false);
    }
  }, [assets]);

  const handleDetail = useCallback(async (id: string) => {
    const row = assets.find((a) => a.id === id) ?? null;
    setDetailAsset(row);
    setDetailRecent(null);
    setDetailLoading(true);
    try {
      const recent = await fetchAssetRecent(id, 20);
      setDetailRecent(recent);
      if (!row) {
        setDetailAsset(assets.find((a) => a.id === id) ?? null);
      }
    } catch {
      setDetailRecent(null);
    } finally {
      setDetailLoading(false);
    }
  }, [assets]);

  const handleFiltersChange = (next: FilterState) => {
    setFilters(next);
    setPage(1);
  };

  const handlePageChange = (nextPage: number) => {
    setPage(nextPage);
    tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setPage(1);
    setAssets([]);
    setTableLoading(true);
    tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (initialLoading && assets.length === 0) {
    return <LoadingShell />;
  }

  if (error && assets.length === 0 && !tableLoading) {
    return (
      <div className="app">
        <div className="error-box">
          <p>{error}</p>
          <p>Avvia il backend con start-backend.bat o start-all.bat</p>
          <button
            type="button"
            onClick={() => {
              setInitialLoading(true);
              setPage(1);
            }}
            style={{ marginTop: "1rem" }}
          >
            Riprova
          </button>
        </div>
      </div>
    );
  }

  const selected =
    selectedChart ?? assets.find((a) => a.id === selectedId) ?? assets[0] ?? null;

  return (
    <div className="app">
      <header className="hero">
        <h1>Analisi investimenti — database globale</h1>
        <p>
          Migliaia di azioni e ETF (USA, Europa, Asia) con paginazione, filtri per regione/tipo e
          cache locale per performance.
        </p>
      </header>

      <div className="disclaimer">
        ⚠️ Strumento educativo. Non consulenza finanziaria. Caricamento paginato: 50–100 titoli
        per pagina per evitare timeout.
      </div>

      <div className="meta-bar">
        <span className="meta-pill">
          Universo:{" "}
          <strong>{(universeStats?.total ?? total).toLocaleString("it-IT")}</strong> titoli
        </span>
        {universeStats?.by_type?.etf != null && (
          <span className="meta-pill">
            ETF: <strong>{universeStats.by_type.etf.toLocaleString("it-IT")}</strong>
          </span>
        )}
        {universeStats?.by_region &&
          Object.entries(universeStats.by_region).map(([r, c]) => (
            <span key={r} className="meta-pill">
              {r}: <strong>{c.toLocaleString("it-IT")}</strong>
            </span>
          ))}
        {universeStats?.primary_price_api && (
          <span className="meta-pill" title="Scelta automatica in base al mercato">
            Prezzi USA: <strong>{universeStats.primary_price_api.usa}</strong>
            {" · "}
            Intl: <strong>{universeStats.primary_price_api.international}</strong>
          </span>
        )}
        {universeStats?.primary_analyst_api && (
          <span className="meta-pill">
            Analisti: <strong>{universeStats.primary_analyst_api}</strong>
          </span>
        )}
        {(tableLoading) && (
          <span className="meta-pill loading-pill">Aggiornamento…</span>
        )}
      </div>

      {!universeStats?.finnhub_configured && (
        <div className="disclaimer info-banner">
          🇺🇸 Ora hai solo titoli <strong>USA</strong> (~5.600). Per Milano, Francoforte, Londra,
          Tokyo, Hong Kong, Canada e resto d&apos;Europa: registrati gratis su{" "}
          <a href="https://finnhub.io/register" target="_blank" rel="noreferrer">
            finnhub.io
          </a>
          , crea il file <code>.env</code> (da <code>.env.example</code>) con{" "}
          <code>FINNHUB_API_KEY</code> e lancia <code>sync-universe.bat --force</code>.
        </div>
      )}

      <FilterBar
        filters={filters}
        onChange={handleFiltersChange}
        resultCount={assets.length}
        totalCount={total}
        page={page}
      />

      <Pagination
        page={page}
        totalPages={totalPages}
        total={total}
        pageSize={pageSize}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
      />

      {chartSample.length > 0 && !tableLoading && (
        <ComparisonChart assets={chartSample} title="Top 10 pagina corrente (base 100)" />
      )}

      {selected && !tableLoading && (
        <PriceChart
          data={selected.chart}
          title={
            chartLoading
              ? `Caricamento grafico ${selected.name}…`
              : `${selected.name} (${selected.country}) — storico (ultimo: ${selected.last_date ?? "—"})`
          }
          color={CHART_COLORS[selected.type] ?? "#3b82f6"}
        />
      )}

      <div ref={tableRef}>
        <h2 className="section-title">Tabella comparativa</h2>
        <p className="section-desc">
          Pagina {page} · ordinata per % Buy (globale) · clicca una riga per il dettaglio.
        </p>

        <AnalystQualityGuide />

        <AssetsTable
          assets={assets}
          selectedId={selectedId}
          loading={tableLoading}
          pageKey={`${page}-${pageSize}`}
          onSelect={handleSelect}
          onDetail={handleDetail}
        />
      </div>

      <AssetDetailModal
        asset={detailAsset}
        recent={detailRecent}
        loading={detailLoading}
        onClose={() => {
          setDetailAsset(null);
          setDetailRecent(null);
        }}
      />

      <Pagination
        page={page}
        totalPages={totalPages}
        total={total}
        pageSize={pageSize}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
      />

      {errors.length > 0 && !tableLoading && (
        <div className="disclaimer" style={{ marginTop: "1.5rem" }}>
          {errors.length} titoli non analizzati in questa pagina (dati mancanti o rate limit).
        </div>
      )}

      <StartupSection region={filters.region} onSelect={handleSelect} />
    </div>
  );
}
