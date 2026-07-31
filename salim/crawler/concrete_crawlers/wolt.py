"""WoltCrawler — concrete crawler for Wolt Market (Israel) grocery prices.

Source (price-transparency index):
    https://wm-gateway.wolt.com/isr-prices/public/v1/index.html

Recon showed a 3-level HTML tree (public, no auth):
    index.html          -> daily pages `YYYY-MM-DD.html` (newest first)
    2026-07-31.html     -> relative `.gz` file links `download/<date>/<name>.gz`
    <name>.gz           -> gzipped price file (Stores / PriceFull / PromoFull),
                           named `<Type><chain>-<store>-[seq-]<YYYYMMDD>-<HHMMSS>.gz`

Subclasses ``Crawler`` directly (not ``HttpIndexCrawler``): it's a two-level
crawl, and the date lives in a `-YYYYMMDD-HHMMSS.gz` suffix — a naive
"first digit run" would grab the chain id instead.

Checkpoint = the newest file timestamp ``YYYYMMDDHHMMSS`` (file-level, so
intraday additions on an already-seen day are still picked up).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from crawler import Crawler, DEFAULT_HEADERS, extract_links

log = logging.getLogger("salim.crawler.wolt")

WOLT_INDEX_URL = "https://wm-gateway.wolt.com/isr-prices/public/v1/index.html"


class WoltCrawler(Crawler):
    """Fetch Wolt Market (IL) grocery price files and upload the new ones."""

    _DAY_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")       # YYYY-MM-DD in a day link
    _TS_RE = re.compile(r"(\d{8})-(\d{6})\.gz$")            # -YYYYMMDD-HHMMSS.gz in a file

    def __init__(self, config, max_days: int | None = None):
        super().__init__(config)
        self.max_days = max_days  # safety cap on day-pages scanned per run
        self._http = requests.Session()
        self._http.headers.update(DEFAULT_HEADERS)

    def _get(self, url: str) -> str:
        resp = self._http.get(url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        return resp.text

    @classmethod
    def _day_date(cls, link: str) -> str | None:
        """`.../2026-07-31.html` -> `20260731` (day-level key)."""
        m = cls._DAY_RE.search(Path(urlparse(link).path).name)
        return "".join(m.groups()) if m else None

    @classmethod
    def _file_ts(cls, link: str) -> str | None:
        """`...-20260731-000032.gz` -> `20260731000032` (14-digit timestamp)."""
        m = cls._TS_RE.search(Path(urlparse(link).path).name)
        return "".join(m.groups()) if m else None

    def fetch(self) -> tuple[list[str], str | None]:
        base = self.config.source_url or WOLT_INDEX_URL

        # Level 1: the index lists dated day-pages.
        days = sorted(
            (d, link)
            for link in extract_links(self._get(base), base)
            if (d := self._day_date(link))
        )
        days.reverse()  # newest day first

        # Only scan day-pages that could hold files newer than the checkpoint.
        since = self._cacher.load()
        if since:
            selected = [link for d, link in days if d >= since[:8]]
        else:
            selected = [link for _, link in days[:1]]  # first run: newest day only
        if self.max_days is not None:
            selected = selected[: self.max_days]

        # Level 2: each day-page lists the actual .gz price files (relative links).
        suffixes = self.config.link_suffixes or (".gz",)
        file_links: list[str] = []
        for day_url in selected:
            file_links.extend(extract_links(self._get(day_url), day_url, suffixes))

        timestamps = [ts for ts in (self._file_ts(link) for link in file_links) if ts]
        candidates = timestamps + ([since] if since else [])  # never regress the mark
        newest = max(candidates) if candidates else None
        log.info(
            "wolt: scanned %d day-page(s), %d file link(s); newest %s",
            len(selected), len(file_links), newest,
        )
        return file_links, newest

    def new_links(self, links: list[str], since_date: str | None) -> list[str]:
        if since_date is None:
            return list(links)
        fresh = [link for link in links if (self._file_ts(link) or "") > since_date]
        log.info("wolt new_links: %d of %d newer than %s", len(fresh), len(links), since_date)
        return fresh
