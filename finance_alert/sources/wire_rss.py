"""Feed RSS wire gratuiti: PR Newswire, GlobeNewswire (nessuna API key)."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from finance_alert.config import Ticker
from finance_alert.http import get_feed
from finance_alert.models import NewsItem

# Feed pubblici stabili (endpoint aperti, UA browser via get_feed)
WIRE_FEEDS: list[tuple[str, str, str]] = [
    (
        "PR Newswire",
        "https://www.prnewswire.com/rss/news-releases-list.rss",
        "https://www.prnewswire.com/",
    ),
    (
        "GlobeNewswire",
        "https://www.globenewswire.com/RssFeed/subjectcode/27-Earnings%20Releases/feedTitle/"
        "GlobeNewswire%20-%20Earnings%20Releases",
        "https://www.globenewswire.com/",
    ),
]

_FEED_TTL_SEC = 120.0
_feed_cache: dict[str, tuple[float, list[dict[str, str | datetime | None]]]] = {}


def _parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    try:
        when = parsedate_to_datetime(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            when = datetime.strptime(text.replace("Z", "+0000"), fmt)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return when
        except ValueError:
            continue
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_feed_xml(xml: str) -> list[dict[str, str | datetime | None]]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    tag = _local_name(root.tag).lower()
    if tag == "rss":
        nodes = root.findall("./channel/item")
    elif tag == "feed":
        nodes = root.findall(".//{*}entry")
        if not nodes:
            nodes = root.findall("./entry")
    else:
        nodes = root.findall(".//item") or root.findall(".//{*}entry")

    rows: list[dict[str, str | datetime | None]] = []
    for node in nodes[:40]:
        title = (node.findtext("title") or "").strip()
        if not title:
            continue
        link = (node.findtext("link") or "").strip()
        if not link:
            alt = node.find("{*}link")
            if alt is not None:
                link = (alt.attrib.get("href") or "").strip()
        published = _parse_datetime(
            node.findtext("pubDate")
            or node.findtext("published")
            or node.findtext("updated")
        )
        rows.append({"headline": title, "url": link, "published": published})
    return rows


def _load_feed(publisher: str, url: str, referer: str) -> list[dict[str, str | datetime | None]]:
    now = time.time()
    hit = _feed_cache.get(url)
    if hit and now - hit[0] < _FEED_TTL_SEC:
        return hit[1]
    xml = get_feed(url, referer=referer)
    if not xml:
        return []
    rows = _parse_feed_xml(xml)
    _feed_cache[url] = (now, rows)
    return rows


def _match_ticker(text: str, watchlist: list[Ticker]) -> str | None:
    upper = text.upper()
    for item in watchlist:
        if re.search(rf"\b{re.escape(item.ticker)}\b", upper):
            return item.ticker
        name = (item.name or "").strip()
        if len(name) >= 4 and re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            return item.ticker
    return None


def fetch_news(watchlist: list[Ticker]) -> list[NewsItem]:
    """Scarica feed wire e filtra per ticker/nome in watchlist."""
    if not watchlist:
        return []
    wanted = {t.ticker for t in watchlist}
    items: list[NewsItem] = []
    seen: set[str] = set()

    for publisher, url, referer in WIRE_FEEDS:
        for row in _load_feed(publisher, url, referer):
            headline = str(row.get("headline") or "")
            link = str(row.get("url") or "")
            key = (link or headline).strip().lower()
            if not headline or not key or key in seen:
                continue
            ticker = _match_ticker(headline, watchlist)
            if ticker is None or ticker not in wanted:
                continue
            seen.add(key)
            items.append(
                NewsItem(
                    ticker=ticker,
                    headline=headline,
                    url=link,
                    published=row.get("published"),  # type: ignore[arg-type]
                    source="wire_rss",
                    publisher=publisher,
                )
            )
    return items


def available() -> bool:
    return True
