from __future__ import annotations

from concrete_crawlers.cerberus import CerberusCrawler


class RamiLeviCrawler(CerberusCrawler):
    """Cerberus-backed crawler for Rami Levi price publications."""

    name = "rami_levi"
