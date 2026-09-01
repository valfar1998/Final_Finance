import xml.etree.ElementTree as ET

from finance_alert.sources.edgar import _parse_atom_filings


SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>8-K - NVIDIA CORP (0001045810) (Filer)</title>
    <link rel="alternate" type="text/html"
      href="https://www.sec.gov/Archives/edgar/data/1045810/0001045810-26-000099-index.htm"/>
    <id>urn:tag:sec.gov,2008:accession-number=0001045810-26-000099</id>
    <updated>2026-09-01T12:00:00-04:00</updated>
  </entry>
  <entry>
    <title>8-K - RANDOM CORP (0009999999) (Filer)</title>
    <link rel="alternate" type="text/html"
      href="https://www.sec.gov/Archives/edgar/data/9999999/0009999999-26-000001-index.htm"/>
    <id>urn:tag:sec.gov,2008:accession-number=0009999999-26-000001</id>
    <updated>2026-09-01T11:00:00-04:00</updated>
  </entry>
</feed>
"""


def test_atom_parser_matches_watchlist_cik():
    cik_to_ticker = {"0001045810": "NVDA"}
    rows = _parse_atom_filings(
        SAMPLE_ATOM,
        cik_to_ticker=cik_to_ticker,
        wanted_forms={"8-K"},
    )
    assert len(rows) == 1
    assert rows[0].ticker == "NVDA"
    assert rows[0].accession == "0001045810-26-000099"
    assert rows[0].form == "8-K"
