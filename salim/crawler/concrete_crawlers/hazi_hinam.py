"""HaziHinamCrawler — concrete crawler for Hazi Hinam (Israel) grocery prices.

Source (price-transparency index):
    https://shop.hazi-hinam.co.il/Prices

Recon: a single-level, server-rendered HTML listing (public, no auth, no XHR
— confirmed via curl), paginated via `?p=<n>&s=&f=&t=&d=` (search / filter /
type / date query params, all left blank here). Each row's download link is
already the final, absolute Azure blob URL, named
`<Type><chain>-<store>-<YYYYMMDD>-<HHMMSS>.gz`.

Checkpoint = the newest file timestamp `YYYYMMDD-HHMMSS` found across all
scanned pages (kept dash-separated, matching this source's own filename shape).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from crawler import Crawler, DEFAULT_HEADERS, extract_links

log = logging.getLogger("salim.crawler.hazi_hinam")

# Only these report types are wanted for this pipeline.
_WANTED_PREFIXES = ("PriceFull", "PromoFull")

_FILE_SUFFIXES = (".gz",)
_DATE_RE = re.compile(r"(\d{8}-\d{6})")  # e.g. PriceFull...-20260806-140025.gz
_MAX_PAGES = 50  # hard cap on pages walked per run; checkpoint + empty-page checks normally stop far earlier


class HaziHinamCrawler(Crawler):
    """Fetch Hazi Hinam PriceFull/PromoFull files and upload the new ones."""

    name = "hazi_hinam"

    @staticmethod
    def _file_date(fname: str) -> str | None:
        match = _DATE_RE.search(fname)
        return match.group(1).replace("-", "") if match else None

    def fetch(self) -> tuple[list[str], str | None]:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)

        # The listing is newest-first, so once a page's wanted files are all
        # already <= the last checkpoint, later pages should be older too --
        # stop paginating instead of walking the whole site every run. This
        # is a soft optimization on an *observed* ordering, not a guarantee
        # the site makes: if it's ever wrong, the worst case is a page of
        # already-seen files gets skipped over early, not silently dropped
        # forever -- _MAX_PAGES is the unconditional backstop either way.
        since = self._cacher.load()

        links: list[str] = []
        seen: set[str] = set()
        pages_walked = 0
        page = 1
        while page <= _MAX_PAGES:
            resp = session.get(
                self.config.source_url,
                params={"p": page, "s": "", "f": "", "t": "", "d": ""},
                timeout=30,
            )
            resp.raise_for_status()
            resp.encoding = resp.encoding or resp.apparent_encoding or "utf-8"
            page_links = extract_links(resp.text, self.config.source_url, _FILE_SUFFIXES)
            wanted_on_page = [
                link for link in page_links
                if Path(urlparse(link).path).name.startswith(_WANTED_PREFIXES)
            ]
            fresh_on_page = [link for link in wanted_on_page if link not in seen]
            if not fresh_on_page:
                break  # empty page, or site clamped back to the last valid page
            seen.update(fresh_on_page)
            links.extend(fresh_on_page)
            pages_walked += 1

            if since and all((self._file_date(link) or "") <= since for link in wanted_on_page):
                break  # rest of the site should be older too, per the ordering note above
            page += 1

        dates = [d for d in (self._file_date(link) for link in links) if d]
        newest = max(dates) if dates else None
        log.info("fetched %d file(s) across %d page(s); newest %s", len(links), pages_walked, newest)
        return links, newest

    def new_links(self, links: list[str], since_date: str | None) -> list[str]:
        if since_date is None:
            return list(links)
        fresh = [link for link in links if (self._file_date(link) or "") > since_date]
        log.info("new_links: %d of %d newer than %s", len(fresh), len(links), since_date)
        return fresh
