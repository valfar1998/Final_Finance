import type { AssetRow } from "./api";

export type RegionFilter = "all" | "usa" | "italia" | "europa" | "uk" | "asia" | "canada";
export type TypeFilter = "all" | "azione" | "etf";
export type SortKey =
  | "buyability_desc"
  | "buyability_asc"
  | "previsione_desc"
  | "previsione_asc"
  | "upside_desc"
  | "prezzo_asc"
  | "prezzo_desc"
  | "rendimento_desc"
  | "ytd_desc";

export interface FilterState {
  region: RegionFilter;
  type: TypeFilter;
  sort: SortKey;
  minBuyability: number;
  minPrevisionePct: number;
  search: string;
}

export const DEFAULT_FILTERS: FilterState = {
  region: "all",
  type: "azione",
  sort: "buyability_desc",
  minBuyability: 0,
  minPrevisionePct: 0,
  search: "",
};

function passesFilters(a: AssetRow, filters: FilterState): boolean {
  if (filters.type !== "all" && a.type !== filters.type) return false;
  if (filters.minBuyability > 0) {
    if (a.buyability_pct == null || a.buyability_pct < filters.minBuyability) return false;
  }
  if (filters.minPrevisionePct > 0) {
    if (
      a.previsione_rendimento_pct == null ||
      a.previsione_rendimento_pct < filters.minPrevisionePct
    ) {
      return false;
    }
  }
  return true;
}

export function filterAssets(assets: AssetRow[], filters: FilterState): AssetRow[] {
  return assets.filter((a) => passesFilters(a, filters));
}

export const REGION_OPTIONS: { value: RegionFilter; label: string }[] = [
  { value: "all", label: "Tutte le regioni" },
  { value: "usa", label: "USA" },
  { value: "italia", label: "Italia" },
  { value: "europa", label: "Europa" },
  { value: "uk", label: "Regno Unito" },
  { value: "asia", label: "Asia" },
  { value: "canada", label: "Canada" },
];

export const TYPE_OPTIONS: { value: TypeFilter; label: string }[] = [
  { value: "all", label: "Tutti i tipi" },
  { value: "azione", label: "Azioni" },
  { value: "etf", label: "ETF" },
];

export const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "buyability_desc", label: "% Buy analisti ↓" },
  { value: "buyability_asc", label: "% Buy analisti ↑" },
  { value: "previsione_desc", label: "Previsione % ↓ (12m)" },
  { value: "previsione_asc", label: "Previsione % ↑ (12m)" },
  { value: "upside_desc", label: "Upside analisti ↓" },
  { value: "prezzo_asc", label: "Prezzo ↑ (economici)" },
  { value: "prezzo_desc", label: "Prezzo ↓" },
  { value: "rendimento_desc", label: "Rend. ann. storico ↓ (ETF)" },
  { value: "ytd_desc", label: "YTD ↓" },
];

export const PREVISIONE_FILTER_OPTIONS = [
  { value: 0, label: "Nessun minimo" },
  { value: 5, label: "Previsione ≥ +5%" },
  { value: 10, label: "Previsione ≥ +10%" },
  { value: 15, label: "Previsione ≥ +15%" },
  { value: 20, label: "Previsione ≥ +20%" },
];
