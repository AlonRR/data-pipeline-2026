"""HttpIndexCrawler — a concrete, generic crawler over a plain HTML file index.

Template to adapt per real source: the login mechanism and the date format
differ per supermarket chain. Here we assume HTTP basic-auth (optional) and a
date embedded in each file name as a run of 8-14 digits (YYYYMMDD[hhmm[ss]]).
Subclass ``Crawler`` and override ``fetch`` / ``new_links`` for other sources.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from crawler import Crawler, DEFAULT_HEADERS, extract_links

log = logging.getLogger("salim.crawler.http")


class HttpIndexCrawler(Crawler):
    _DATE_RE = re.compile(r"(\d{8,14})")

    def _session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        if self.config.user_name:
            session.auth = (self.config.user_name, self.config.password or "")
        return session

    @classmethod
    def _link_date(cls, link: str) -> str | None:
        match = cls._DATE_RE.search(Path(urlparse(link).path).name)
        return match.group(1) if match else None

    def fetch(self) -> tuple[list[str], str | None]:
        resp = self._session().get(self.config.source_url, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        links = extract_links(resp.text, self.config.source_url, self.config.link_suffixes)
        dates = [d for d in (self._link_date(link) for link in links) if d]
        newest = max(dates) if dates else None  # dates share a format -> lexical max is chronological
        log.info("fetched %d link(s); newest date %s", len(links), newest)
        return links, newest

    def new_links(self, links: list[str], since_date: str | None) -> list[str]:
        if since_date is None:
            return list(links)
        fresh = [link for link in links if (self._link_date(link) or "") > since_date]
        log.info("new_links: %d of %d newer than %s", len(fresh), len(links), since_date)
        return fresh
