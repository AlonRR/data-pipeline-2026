"""Shufersal crawler — public price listing at prices.shufersal.co.il.

No login: the listing is a plain paged HTML table at
``/FileObject/UpdateCategory?catID=<n>&storeId=0&page=<n>``. We take the two
"full snapshot" categories and skip the incremental deltas.

The wrinkle is that each row's download link is an Azure blob URL carrying a
SAS token minted at listing time and valid for only ~30 minutes. A cold first
run is ~880 files, long enough for the tail of that list to rot before the
shared pipeline gets to it — so links are re-minted on the way out, see
``_FreshLinkDownloader``.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from crawler import DEFAULT_HEADERS, Crawler, Downloader, extract_links

log = logging.getLogger("salim.crawler.shufersal")

# catID 1=price, 2=pricefull, 3=promo, 4=promofull, 5=stores. We want the full
# snapshots only — the deltas are useless without replaying every prior file.
_WANTED_CATEGORIES = (2, 4)

_STORE_ID = 0  # all branches

_BLOB_HOST = "pricesprodpublic.blob.core.windows.net"

# Re-mint a link this long before its SAS token lapses. Listing a page is slow
# (10-20s observed), so the margin has to cover a refresh plus the download.
_SAS_MARGIN = timedelta(minutes=2)

_DATE_RE = re.compile(r"(\d{8})-(\d{6})")  # PriceFull...-20260802-030000.gz
_PAGE_RE = re.compile(r"page=(\d+)")  # unanchored: hrefs arrive HTML-escaped, as &amp;page=


def _file_name(url: str) -> str:
    return Path(urlparse(url).path).name


def _file_date(url: str) -> str | None:
    match = _DATE_RE.search(_file_name(url))
    return "".join(match.groups()) if match else None


def _sas_expiry(url: str) -> datetime | None:
    """Read the ``se`` (signed expiry) parameter out of a blob URL."""
    raw = parse_qs(urlparse(url).query).get("se", [None])[0]
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        log.warning("unparseable SAS expiry %r", raw)
        return None


def _is_fresh(url: str | None, margin: timedelta) -> bool:
    """Whether *url*'s SAS token still has more than *margin* left to live."""
    if not url:
        return False
    expiry = _sas_expiry(url)
    return expiry is None or expiry - datetime.now(timezone.utc) > margin


class _FreshLinkDownloader(Downloader):
    """Downloader that re-mints Shufersal's SAS links before they expire.

    The base pipeline lists every link up front and only then downloads them
    one by one, so on a long run the later links are already dead by the time
    their turn comes. Re-minting is cheap because one listing request refreshes
    a whole page of 20 links at once — ``refresh`` is expected to serve the
    other 19 from that same response without going back to the network.
    """

    def __init__(self, dest_dir, refresh, margin: timedelta):
        super().__init__(dest_dir)
        self._refresh = refresh
        self._margin = margin

    def download(self, links) -> list[Path]:
        paths: list[Path] = []
        for url in links:
            name = _file_name(url)
            if not _is_fresh(url, self._margin):
                url = self._refresh(name)
            try:
                paths += super().download([url])
            except requests.HTTPError as exc:
                # Expired between the freshness check and the request.
                if exc.response is None or exc.response.status_code != 403:
                    raise
                log.info("403 on %s; re-minting link", name)
                paths += super().download([self._refresh(name, force=True)])
        return paths


class ShufersalCrawler(Crawler):
    """Lists PriceFull/PromoFull files across every Shufersal branch."""

    name = "shufersal"

    def __init__(self, config):
        super().__init__(config)
        parsed = urlparse(config.source_url)
        self._base_url = f"{parsed.scheme}://{parsed.netloc}"
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._links: dict[str, str] = {}          # file name -> current URL
        self._origin: dict[str, tuple[int, int]] = {}  # file name -> (catID, page)
        self._downloader = _FreshLinkDownloader(
            config.download_dir, self._refresh_link, _SAS_MARGIN
        )

    # --- listing --- #
    def _page_html(self, cat_id: int, page: int) -> str:
        url = f"{self._base_url}/FileObject/UpdateCategory"
        resp = self._session.get(
            url,
            params={"catID": cat_id, "storeId": _STORE_ID, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _page_count(html: str) -> int:
        """Highest page number offered by the pager row.

        Needed because an out-of-range page still returns rows — listing until
        a page comes back empty would never terminate.
        """
        pages = [int(n) for n in _PAGE_RE.findall(html)]
        return max(pages) if pages else 1

    def _record_page(self, cat_id: int, page: int, html: str) -> list[str]:
        """Index every download link on one listing page; return their names."""
        links = [
            link for link in extract_links(html, self._base_url)
            if urlparse(link).netloc == _BLOB_HOST
        ]
        names = []
        for link in links:
            name = _file_name(link)
            self._links[name] = link
            self._origin[name] = (cat_id, page)
            names.append(name)
        return names

    def _index_category(self, cat_id: int) -> None:
        first = self._page_html(cat_id, 1)
        total = self._page_count(first)
        self._record_page(cat_id, 1, first)
        for page in range(2, total + 1):
            self._record_page(cat_id, page, self._page_html(cat_id, page))
        log.info("catID=%d: indexed %d page(s)", cat_id, total)

    def _refresh_link(self, name: str, force: bool = False) -> str:
        """Return a live URL for *name*, re-listing its page only when needed.

        Re-listing refreshes all 20 links on that page at once, so the rest of
        the page is then served from memory — one request per page, not per file.
        """
        cat_id, page = self._origin[name]
        if not force and _is_fresh(self._links.get(name), _SAS_MARGIN):
            return self._links[name]

        if name in self._record_page(cat_id, page, self._page_html(cat_id, page)):
            log.info("re-minted catID=%d page=%d for %s", cat_id, page, name)
            return self._links[name]

        # New uploads shift the listing, so a file can drift off its original
        # page mid-run. Rebuilding the category is expensive but rare.
        log.warning("%s not on catID=%d page=%d; re-indexing category", name, cat_id, page)
        self._index_category(cat_id)
        if name not in self._links:
            raise RuntimeError(f"{name} disappeared from the Shufersal listing")
        return self._links[name]

    # --- source-specific pipeline steps --- #
    def fetch(self) -> tuple[list[str], str | None]:
        self._links.clear()
        self._origin.clear()
        for cat_id in _WANTED_CATEGORIES:
            self._index_category(cat_id)

        links = list(self._links.values())
        dates = [d for d in (_file_date(link) for link in links) if d]
        newest = max(dates) if dates else None  # fixed-width -> lexical max is chronological
        log.info("fetched %d file(s); newest %s", len(links), newest)
        return links, newest

    def new_links(self, links: list[str], since_date: str | None) -> list[str]:
        if since_date is None:
            return list(links)
        fresh = [link for link in links if (_file_date(link) or "") > since_date]
        log.info("new_links: %d of %d newer than %s", len(fresh), len(links), since_date)
        return fresh
