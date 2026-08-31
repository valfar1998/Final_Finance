from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def _num(value: Any) -> float | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Quote:
    ticker: str
    price: float | None = None
    previous_close: float | None = None
    change_pct: float | None = None
    source: str = ""
    ts: datetime | None = None
    session: str = "regular"
    volume: float | None = None
    avg_volume: float | None = None
    rvol: float | None = None

    def pct_from_close(self) -> float | None:
        if self.change_pct is not None:
            return self.change_pct
        if self.price is None or not self.previous_close:
            return None
        return (self.price - self.previous_close) / self.previous_close * 100.0


@dataclass
class EarningsEvent:
    ticker: str
    date: str
    hour: str = ""
    eps_actual: float | None = None
    eps_estimate: float | None = None
    revenue_actual: float | None = None
    revenue_estimate: float | None = None
    source: str = ""

    @property
    def reported(self) -> bool:
        return self.eps_actual is not None or self.revenue_actual is not None

    def eps_surprise_pct(self) -> float | None:
        if self.eps_actual is None or self.eps_estimate in (None, 0):
            return None
        return (self.eps_actual - self.eps_estimate) / abs(self.eps_estimate) * 100.0

    def revenue_surprise_pct(self) -> float | None:
        if self.revenue_actual is None or self.revenue_estimate in (None, 0):
            return None
        return (self.revenue_actual - self.revenue_estimate) / abs(self.revenue_estimate) * 100.0


@dataclass
class NewsItem:
    ticker: str
    headline: str
    url: str = ""
    published: datetime | None = None
    source: str = ""
    publisher: str = ""
    score: int = 0
    matched: list[str] = field(default_factory=list)
    llm_driver: str = ""
    llm_provider: str = ""


@dataclass
class Filing:
    ticker: str
    form: str
    accession: str
    filed: str
    items: str = ""
    url: str = ""
    source: str = "sec_edgar"


@dataclass
class Alert:
    key: str
    tipo: str
    ticker: str
    titolo: str
    body: str
    severity: str = "medium"
    url: str | None = None
    setup_score: int = 0
    verdict: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_num(value: Any) -> float | None:
    return _num(value)
