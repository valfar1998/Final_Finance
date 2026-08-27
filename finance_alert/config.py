from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from finance_alert.env import ROOT

CONFIG_PATH = ROOT / "config" / "watchlist.yaml"


@dataclass
class Ticker:
    ticker: str
    name: str = ""
    cik: str = ""

    def __post_init__(self) -> None:
        self.ticker = str(self.ticker).strip().upper()
        self.name = str(self.name or self.ticker).strip()
        self.cik = str(self.cik or "").strip()


@dataclass
class Rules:
    spike_pct: float = 3.0
    spike_buckets: list[float] = field(default_factory=lambda: [3, 5, 7, 10, 15])
    momentum_pct: float = 2.5
    momentum_minutes: int = 30
    surprise_eps_pct: float = 3.0
    surprise_revenue_pct: float = 3.0
    earnings_lookahead_hours: int = 36
    news_max_age_hours: int = 8
    news_min_score: int = 3
    news_keywords: list[tuple[str, int]] = field(default_factory=list)
    extended_hours_pct: float = 2.5
    peer_lag_leader_pct: float = 4.0
    peer_lag_max_pct: float = 1.5
    news_block_publishers: list[str] = field(default_factory=list)
    news_boost_publishers: list[str] = field(default_factory=list)
    news_opinion_publishers: list[str] = field(default_factory=list)
    news_opinion_need: list[str] = field(default_factory=list)
    # Solo segnali utili a “cosa può salire” prima / all’inizio del movimento
    enabled_tipos: list[str] = field(default_factory=list)
    only_upside: bool = False
    filing_items_only: list[str] = field(default_factory=list)


@dataclass
class Cluster:
    name: str
    tickers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = str(self.name or "cluster").strip()
        self.tickers = [str(t).strip().upper() for t in self.tickers if str(t).strip()]


@dataclass
class EdgarConfig:
    enabled: bool = True
    forms: list[str] = field(default_factory=lambda: ["8-K", "8-K/A"])
    max_age_hours: int = 24


@dataclass
class AppConfig:
    watchlist: list[Ticker]
    rules: Rules
    edgar: EdgarConfig
    clusters: list[Cluster] = field(default_factory=list)

    @property
    def symbols(self) -> list[str]:
        return [t.ticker for t in self.watchlist]

    def by_symbol(self, symbol: str) -> Ticker | None:
        up = symbol.upper()
        for item in self.watchlist:
            if item.ticker == up:
                return item
        return None


def _keywords(raw: Any) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, (list, tuple)) and item:
            word = str(item[0]).strip().lower()
            score = int(item[1]) if len(item) > 1 else 3
            if word:
                out.append((word, score))
        elif isinstance(item, str) and item.strip():
            out.append((item.strip().lower(), 3))
    return out


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip().lower() for x in raw if str(x).strip()]


def load_config(path: Path | None = None) -> AppConfig:
    target = path or CONFIG_PATH
    data: dict[str, Any] = {}
    if target.is_file():
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data = loaded

    watchlist: list[Ticker] = []
    for row in data.get("watchlist") or []:
        if isinstance(row, str):
            watchlist.append(Ticker(ticker=row))
        elif isinstance(row, dict) and row.get("ticker"):
            watchlist.append(
                Ticker(
                    ticker=str(row["ticker"]),
                    name=str(row.get("name") or ""),
                    cik=str(row.get("cik") or ""),
                )
            )
    if not watchlist:
        watchlist = [Ticker(ticker="NVDA", name="NVIDIA", cik="0001045810")]

    raw_rules = data.get("rules") or {}
    rules = Rules(
        spike_pct=float(os.getenv("SPIKE_PCT") or raw_rules.get("spike_pct") or 3.0),
        spike_buckets=[float(x) for x in (raw_rules.get("spike_buckets") or [3, 5, 7, 10, 15])],
        momentum_pct=float(raw_rules.get("momentum_pct") or 2.5),
        momentum_minutes=int(raw_rules.get("momentum_minutes") or 30),
        surprise_eps_pct=float(
            os.getenv("SURPRISE_EPS_PCT") or raw_rules.get("surprise_eps_pct") or 3.0
        ),
        surprise_revenue_pct=float(raw_rules.get("surprise_revenue_pct") or 3.0),
        earnings_lookahead_hours=int(raw_rules.get("earnings_lookahead_hours") or 36),
        news_max_age_hours=int(raw_rules.get("news_max_age_hours") or 8),
        news_min_score=int(raw_rules.get("news_min_score") or 3),
        news_keywords=_keywords(raw_rules.get("news_keywords")),
        extended_hours_pct=float(raw_rules.get("extended_hours_pct") or 2.5),
        peer_lag_leader_pct=float(raw_rules.get("peer_lag_leader_pct") or 4.0),
        peer_lag_max_pct=float(raw_rules.get("peer_lag_max_pct") or 1.5),
        news_block_publishers=_str_list(raw_rules.get("news_block_publishers")),
        news_boost_publishers=_str_list(raw_rules.get("news_boost_publishers")),
        news_opinion_publishers=_str_list(raw_rules.get("news_opinion_publishers")),
        news_opinion_need=_str_list(raw_rules.get("news_opinion_need")),
        enabled_tipos=_str_list(raw_rules.get("enabled_tipos")),
        only_upside=bool(raw_rules.get("only_upside", False)),
        filing_items_only=[str(x).strip() for x in (raw_rules.get("filing_items_only") or []) if str(x).strip()],
    )
    raw_edgar = data.get("edgar") or {}
    edgar = EdgarConfig(
        enabled=bool(raw_edgar.get("enabled", True)),
        forms=[str(x) for x in (raw_edgar.get("forms") or ["8-K", "8-K/A"])],
        max_age_hours=int(raw_edgar.get("max_age_hours") or 24),
    )
    clusters: list[Cluster] = []
    for row in data.get("clusters") or []:
        if isinstance(row, dict) and row.get("tickers"):
            clusters.append(
                Cluster(name=str(row.get("name") or "cluster"), tickers=list(row.get("tickers") or []))
            )
    return AppConfig(watchlist=watchlist, rules=rules, edgar=edgar, clusters=clusters)
