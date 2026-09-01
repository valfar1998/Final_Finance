from datetime import datetime, timezone
from unittest.mock import patch

from finance_alert.config import Ticker
from finance_alert.http import FEED_HEADERS, get_feed
from finance_alert.sources import wire_rss


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>NVIDIA raised guidance after beat estimates</title>
      <link>https://www.prnewswire.com/news-releases/nvda-test</link>
      <pubDate>Mon, 01 Sep 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Unrelated company announces partnership</title>
      <link>https://www.prnewswire.com/news-releases/other</link>
      <pubDate>Mon, 01 Sep 2026 07:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_feed_headers_use_browser_user_agent():
    assert "Mozilla" in FEED_HEADERS["User-Agent"]
    assert "Python-urllib" not in FEED_HEADERS["User-Agent"]
    assert "rss" in FEED_HEADERS["Accept"] or "xml" in FEED_HEADERS["Accept"]


def test_parse_wire_rss_matches_watchlist():
    watchlist = [Ticker(ticker="NVDA", name="NVIDIA")]
    with patch("finance_alert.sources.wire_rss.get_feed", return_value=SAMPLE_RSS):
        wire_rss._feed_cache.clear()
        items = wire_rss.fetch_news(watchlist)
    assert len(items) == 1
    assert items[0].ticker == "NVDA"
    assert items[0].publisher == "PR Newswire"
    assert items[0].source == "wire_rss"


def test_get_feed_passes_custom_headers():
    with patch("finance_alert.http.get_text", return_value="<rss/>") as mock:
        out = get_feed("https://www.prnewswire.com/rss/test.rss", referer="https://www.prnewswire.com/")
    assert out == "<rss/>"
    headers = mock.call_args.kwargs["headers"]
    assert "Mozilla" in headers["User-Agent"]
    assert headers["Referer"] == "https://www.prnewswire.com/"
