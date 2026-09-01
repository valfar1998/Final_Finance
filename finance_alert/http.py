from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, TypeVar

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

FEED_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

T = TypeVar("T")
R = TypeVar("R")


def map_parallel(
    fn: Callable[[T], R],
    items: list[T],
    *,
    max_workers: int = 8,
) -> list[R]:
    """Applica fn su items in parallelo (ordine stabile)."""
    if not items:
        return []
    if len(items) == 1:
        return [fn(items[0])]
    workers = max(1, min(max_workers, len(items)))
    out: list[R] = [None] * len(items)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, item): idx for idx, item in enumerate(items)}
        for fut in as_completed(futures):
            out[futures[fut]] = fut.result()
    return out


class HttpError(RuntimeError):
    def __init__(self, url: str, status: int, body: str = "") -> None:
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status} {url}")


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
    retries: int = 2,
) -> Any:
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}{'&' if '?' in url else '?'}{qs}"
    req_headers = {"User-Agent": DEFAULT_UA, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=req_headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            if not text.strip():
                return None
            return json.loads(text)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            if exc.code in {429, 500, 502, 503} and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                last_exc = HttpError(url, exc.code, body)
                continue
            raise HttpError(url, exc.code, body) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc
    return None


def get_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> str:
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}{'&' if '?' in url else '?'}{qs}"
    req_headers = {"User-Agent": DEFAULT_UA}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_feed(
    url: str,
    *,
    referer: str | None = None,
    timeout: float = 25.0,
) -> str | None:
    """Fetch RSS/Atom con User-Agent browser (evita 403 da Python-urllib default)."""
    headers = dict(FEED_HEADERS)
    if referer:
        headers["Referer"] = referer
    try:
        return get_text(url, headers=headers, timeout=timeout)
    except (HttpError, OSError, TimeoutError, urllib.error.URLError):
        return None
