"""Optional Playwright script to download Stooq CSV when HTTP is blocked by JS challenge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from assets import DEFAULT_ASSETS  # noqa: E402
from services.stooq import CACHE_DIR, _cache_path, _is_valid_csv  # noqa: E402

CSV_URLS = (
    "https://stooq.com/q/d/l/?s={symbol}&i=d",
    "https://stooq.pl/q/d/l/?s={symbol}&i=d",
)


def _navigation_aborted_for_download(exc: BaseException) -> bool:
    msg = str(exc)
    return (
        "Download is starting" in msg
        or "net::ERR_ABORTED" in msg
        or "NS_BINDING_ABORTED" in msg
    )


def _save_if_valid(symbol: str, text: str, out: Path) -> bool:
    if _is_valid_csv(text):
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"  OK   {symbol} -> {out.name}")
        return True
    return False


def _try_request(context, symbol: str, out: Path) -> bool:
    """Fetch CSV with browser cookies (no navigation → no ERR_ABORTED)."""
    for template in CSV_URLS:
        url = template.format(symbol=symbol)
        try:
            resp = context.request.get(url, timeout=60_000)
            if resp.ok and _save_if_valid(symbol, resp.text(), out):
                return True
        except Exception:
            continue
    return False


def _try_download(page, symbol: str, out: Path) -> bool:
    """Navigate to CSV URL and capture the file download."""
    last_error: Exception | None = None
    for template in CSV_URLS:
        url = template.format(symbol=symbol)
        try:
            with page.expect_download(timeout=90_000) as download_info:
                try:
                    page.goto(url, wait_until="commit", timeout=90_000)
                except Exception as exc:
                    # Chrome aborts navigation when a download starts.
                    if not _navigation_aborted_for_download(exc):
                        raise
            download = download_info.value
            download.save_as(out)
            text = out.read_text(encoding="utf-8", errors="replace")
            if _save_if_valid(symbol, text, out):
                return True
            out.unlink(missing_ok=True)
            preview = text.strip().replace("\n", " ")[:80]
            print(f"  FAIL {symbol}: file non valido ({preview!r})")
            return False
        except Exception as exc:
            last_error = exc
            continue
    print(f"  FAIL {symbol}: {last_error}")
    return False


def download_symbol(page, context, symbol: str) -> bool:
    out = _cache_path(symbol)
    if _try_request(context, symbol, out):
        return True
    return _try_download(page, symbol, out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scarica CSV Stooq via browser headless")
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="Simboli Stooq (es. aapl.us). Default: tutti gli asset configurati.",
    )
    args = parser.parse_args()
    symbols = args.symbols or [a["stooq"] for a in DEFAULT_ASSETS]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Installa Playwright: pip install playwright && playwright install chromium")
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        # Passa challenge JS visitando la home
        page.goto("https://stooq.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        for sym in symbols:
            if download_symbol(page, context, sym.lower()):
                ok += 1
            page.wait_for_timeout(500)
        browser.close()

    print(f"\nCompletato: {ok}/{len(symbols)} CSV in {CACHE_DIR}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
