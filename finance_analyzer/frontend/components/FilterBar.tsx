"use client";

import { useEffect, useState } from "react";
import type { FilterState } from "@/lib/filters";
import {
  REGION_OPTIONS,
  TYPE_OPTIONS,
  SORT_OPTIONS,
  PREVISIONE_FILTER_OPTIONS,
} from "@/lib/filters";

interface Props {
  filters: FilterState;
  onChange: (filters: FilterState) => void;
  resultCount: number;
  totalCount: number;
  page?: number;
}

export default function FilterBar({
  filters,
  onChange,
  resultCount,
  totalCount,
  page,
}: Props) {
  const [searchDraft, setSearchDraft] = useState(filters.search);

  useEffect(() => {
    setSearchDraft(filters.search);
  }, [filters.search]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = searchDraft.trim();
      if (next === filters.search) return;
      onChange({ ...filters, search: next });
    }, 350);
    return () => window.clearTimeout(timer);
    // Solo searchDraft: debounce digitazione; filters/onChange letti al tick
  }, [searchDraft]);

  const set = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    onChange({ ...filters, [key]: value });
  };

  const searchActive = filters.search.length >= 2;

  return (
    <div className="filter-bar">
      <div className="filter-row">
        <label className="filter-field filter-field-search">
          <span>Cerca titolo</span>
          <input
            type="search"
            className="filter-search-input"
            placeholder="Nome, ticker (es. Apple, AAPL, ENEL)"
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>

        <label className="filter-field">
          <span>Regione / Paese</span>
          <select
            value={filters.region}
            onChange={(e) => set("region", e.target.value as FilterState["region"])}
          >
            {REGION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-field">
          <span>Tipo asset</span>
          <select
            value={filters.type}
            onChange={(e) => set("type", e.target.value as FilterState["type"])}
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-field">
          <span>Ordina per</span>
          <select
            value={filters.sort}
            onChange={(e) => set("sort", e.target.value as FilterState["sort"])}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-field">
          <span>Min. % Buy analisti</span>
          <select
            value={filters.minBuyability}
            onChange={(e) => set("minBuyability", Number(e.target.value))}
          >
            <option value={0}>Nessun minimo</option>
            <option value={40}>≥ 40%</option>
            <option value={50}>≥ 50%</option>
            <option value={60}>≥ 60%</option>
            <option value={70}>≥ 70%</option>
            <option value={80}>≥ 80%</option>
          </select>
        </label>

        <label className="filter-field">
          <span>Previsione min. (12m)</span>
          <select
            value={filters.minPrevisionePct}
            onChange={(e) => set("minPrevisionePct", Number(e.target.value))}
          >
            {PREVISIONE_FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="filter-count">
        Pagina <strong>{page ?? 1}</strong> · mostrati <strong>{resultCount}</strong> titoli
        {searchActive && (
          <>
            {" "}
            per «<strong>{filters.search}</strong>»
          </>
        )}
        {filters.minBuyability > 0 || filters.minPrevisionePct > 0 ? " (dopo filtri)" : ""} ·{" "}
        {searchActive ? (
          <>
            <strong>{totalCount.toLocaleString("it-IT")}</strong> corrispondenze
          </>
        ) : (
          <>
            universo <strong>{totalCount.toLocaleString("it-IT")}</strong> titoli
          </>
        )}
      </p>
    </div>
  );
}
