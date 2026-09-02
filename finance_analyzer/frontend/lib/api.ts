export interface ChartPoint {
  date: string;
  close: number;
}

export interface AssetRow {
  id: string;
  name: string;
  symbol: string;
  type: "azione" | "etf";
  region: string;
  country: string;
  is_startup_candidate?: boolean;
  stooq_symbol: string;
  yf_ticker?: string;
  price_source?: string;
  rendimento_annuo_pct: number | null;
  ytd_pct: number | null;
  volatilita_annua_pct: number | null;
  max_drawdown_pct: number | null;
  buyability_pct: number | null;
  analyst_label: string;
  analyst_count: number;
  analyst_source?: string;
  analyst_target_mean?: number | null;
  analyst_target_low?: number | null;
  analyst_target_high?: number | null;
  analyst_upside_pct?: number | null;
  analyst_target_spread_pct?: number | null;
  analyst_consensus_date?: string | null;
  analyst_last_rating_date?: string | null;
  analyst_last_target_date?: string | null;
  analyst_last_firm?: string | null;
  market_cap?: number | null;
  valore_atteso?: number | null;
  current_price: number | null;
  previsione_prezzo: number | null;
  previsione_range_basso: number | null;
  previsione_range_alto: number | null;
  previsione_rendimento_pct: number | null;
  previsione_note?: string;
  chart: ChartPoint[];
  data_points: number;
  last_date: string | null;
}

export interface DashboardParams {
  page?: number;
  page_size?: number;
  region?: string;
  type?: string;
  sort?: string;
  min_buyability?: number;
  min_previsione_pct?: number;
  q?: string;
}

export interface RecentBarsResponse {
  id: string;
  name: string;
  stooq_symbol: string;
  yf_ticker: string;
  bars: ChartPoint[];
  source: string;
  count: number;
  from_date: string | null;
  to_date: string | null;
}

export interface DashboardResponse {
  assets: AssetRow[];
  startups?: AssetRow[];
  errors: { id: string; name: string; error: string }[];
  count: number;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  regions?: { id: string; label: string }[];
}

export interface StartupsParams {
  region?: string;
  min_analysts?: number;
  max_target_spread_pct?: number;
}

export interface StartupsResponse {
  startups: AssetRow[];
  count: number;
  filters_applied?: {
    min_analysts: number;
    max_target_spread_pct: number;
  };
}

export interface UniverseStats {
  total: number;
  by_region: Record<string, number>;
  by_type?: Record<string, number>;
  last_sync: string | null;
  last_etf_sync?: string | null;
  finnhub_configured: boolean;
  fmp_configured?: boolean;
  twelve_data_configured?: boolean;
  primary_price_api?: { usa: string; international: string };
  primary_analyst_api?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchDashboard(params: DashboardParams = {}): Promise<DashboardResponse> {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.page_size) q.set("page_size", String(params.page_size));
  if (params.region) q.set("region", params.region);
  if (params.type) q.set("type", params.type);
  if (params.sort) q.set("sort", params.sort);
  if (params.min_buyability != null && params.min_buyability > 0) {
    q.set("min_buyability", String(params.min_buyability));
  }
  if (params.min_previsione_pct != null && params.min_previsione_pct > 0) {
    q.set("min_previsione_pct", String(params.min_previsione_pct));
  }
  if (params.q && params.q.trim().length >= 2) {
    q.set("q", params.q.trim());
  }

  const res = await fetch(`${API_BASE}/api/dashboard?${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Errore nel caricamento dashboard");
  return res.json();
}

export async function fetchAsset(id: string): Promise<AssetRow> {
  const res = await fetch(`${API_BASE}/api/asset/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Asset non trovato");
  return res.json();
}

export async function fetchAssetRecent(id: string, days = 20): Promise<RecentBarsResponse> {
  const res = await fetch(`${API_BASE}/api/asset/${id}/recent?days=${days}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Dati recenti non disponibili");
  return res.json();
}

export async function fetchStartups(params: StartupsParams = {}): Promise<StartupsResponse> {
  const q = new URLSearchParams();
  const region = params.region ?? "all";
  if (region && region !== "all") q.set("region", region);
  if (params.min_analysts != null && params.min_analysts > 0) {
    q.set("min_analysts", String(params.min_analysts));
  }
  if (params.max_target_spread_pct != null && params.max_target_spread_pct > 0) {
    q.set("max_target_spread_pct", String(params.max_target_spread_pct));
  }
  const res = await fetch(`${API_BASE}/api/startups?${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Errore caricamento startup");
  return res.json();
}

export async function fetchUniverseStats(): Promise<UniverseStats> {
  const res = await fetch(`${API_BASE}/api/universe/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error("Errore stats universo");
  return res.json();
}
