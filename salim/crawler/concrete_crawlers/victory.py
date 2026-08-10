from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from crawler import Crawler, DEFAULT_HEADERS

log = logging.getLogger("salim.crawler.victory")

_CHAIN_IDS = ("7290696200003", "7290058103393")
_PRIMARY_CHAIN_ID = _CHAIN_IDS[0]
_WANTED_PREFIXES = ("PriceFull", "PromoFull")
_WANTED_FILE_TYPES = {"pricefull", "promofull"}

# Supports YYYYMMDD, YYYYMMDDHHMM, YYYYMMDDHHMMSS and a separator before time.
_DATE_RE = re.compile(r"(?<!\d)(20\d{6})(?:[-_]?(\d{6}|\d{4}))?(?!\d)")


class VictoryCrawler(Crawler):
    """Download Victory PriceFull/PromoFull files from the Laibcatalog API."""

    name = "victory"

    def _session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        return session

    @property
    def _base_url(self) -> str:
        parsed = urlparse(self.config.source_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @classmethod
    def _file_date(cls, link_or_name: str) -> str | None:
        """Return a sortable YYYYMMDDHHMMSS timestamp extracted from a filename."""
        name = Path(urlparse(link_or_name).path).name
        matches = list(_DATE_RE.finditer(name))
        if not matches:
            return None

        day, time_part = matches[-1].groups()
        if time_part is None:
            time_part = "000000"
        elif len(time_part) == 4:
            time_part += "00"
        return day + time_part

    @staticmethod
    def _entries(payload) -> list[dict]:
        """Accept both a direct JSON list and common API wrapper objects."""
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("files", "data", "items", "result"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise RuntimeError("unexpected Victory getfiles response format")

    @staticmethod
    def _wanted(entry: dict) -> bool:
        file_name = str(entry.get("fileName") or "")
        file_type = str(entry.get("fileType") or "").lower()
        return file_name.startswith(_WANTED_PREFIXES) or file_type in _WANTED_FILE_TYPES

    @staticmethod
    def _normalize_threshold(value: str | None) -> str | None:
        if not value:
            return None
        digits = re.sub(r"\D", "", value)
        if len(digits) == 8:
            return digits + "000000"
        if len(digits) == 12:
            return digits + "00"
        if len(digits) == 14:
            return digits
        raise ValueError(
            "date must use YYYYMMDD, YYYYMMDDHHMM, or YYYYMMDDHHMMSS"
        )

    def fetch(self) -> tuple[list[str], str | None]:
        session = self._session()
        links_by_name: dict[str, str] = {}

        for chain_id in _CHAIN_IDS:
            response = session.get(
                f"{self._base_url}/webapi/api/getfiles",
                params={"edi": chain_id},
                timeout=60,
            )
            if response.status_code == 400:
                log.warning("Victory chain %s returned 400; skipping it", chain_id)
                continue
            response.raise_for_status()

            for entry in self._entries(response.json()):
                file_name = str(entry.get("fileName") or "").strip()
                if not file_name or not self._wanted(entry):
                    continue

                # The public catalog exposes Victory downloads under the primary EDI.
                links_by_name.setdefault(
                    file_name,
                    f"{self._base_url}/webapi/{_PRIMARY_CHAIN_ID}/{quote(file_name)}",
                )

        links = list(links_by_name.values())
        dates = [date for date in (self._file_date(link) for link in links) if date]
        newest = max(dates) if dates else None
        log.info("fetched %d Victory file(s); newest date %s", len(links), newest)
        return links, newest

    def new_links(self, links: list[str], since_date: str | None) -> list[str]:
        """Filter by cached checkpoint, or by the initial configured start date."""
        cached_threshold = self._normalize_threshold(since_date)
        if cached_threshold is not None:
            fresh = [
                link
                for link in links
                if (self._file_date(link) or "") > cached_threshold
            ]
            log.info(
                "new_links: %d of %d newer than checkpoint %s",
                len(fresh),
                len(links),
                cached_threshold,
            )
            return fresh

        start_threshold = self._normalize_threshold(
            os.environ.get("CRAWLER_VICTORY_START_DATE")
        )
        if start_threshold is None:
            return list(links)

        fresh = [
            link
            for link in links
            if (self._file_date(link) or "") >= start_threshold
        ]
        log.info(
            "new_links: %d of %d on/after configured start date %s",
            len(fresh),
            len(links),
            start_threshold,
        )
        return fresh
