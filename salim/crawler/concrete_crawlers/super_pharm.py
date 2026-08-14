from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from crawler import Crawler, DEFAULT_HEADERS

log = logging.getLogger("salim.crawler.super_pharm")

# Match YYYYMMDD-HHMMSS inside filenames, e.g. Price...-20260806-194047.gz
_DATE_RE = re.compile(r"(\d{8}-\d{6})")


class SuperPharmCrawler(Crawler):
    """Fetches Price/Promo files from the public Super-Pharm price transparency site."""

    name = "super_pharm"

    def __init__(self, config):
        super().__init__(config)
        # Keep scheme+host so relative hrefs can be turned into absolute URLs
        parsed = urlparse(config.source_url)
        self._base_url = f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _file_date(fname: str) -> str | None:
        """Extracts YYYYMMDDHHMMSS string from filename for easy lexicographical comparison."""
        match = _DATE_RE.search(fname)
        # Drop the hyphen so dates compare as plain strings (YYYYMMDDHHMMSS)
        return match.group(1).replace("-", "") if match else None

    def fetch(self) -> tuple[list[str], str | None]:
        """Scrape the Super-Pharm index page; return all file links and the newest date."""
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)

        # Download the HTML listing of available price/promo files
        log.info("fetching Super-Pharm index page: %s", self.config.source_url)
        resp = session.get(self.config.source_url, timeout=30)
        resp.raise_for_status()

        # Table rows under .gzTable hold one file each; download link is in column 6
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select(".gzTable tbody tr")

        links: list[str] = []
        dates: list[str] = []

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 6:
                continue

            # Column index 5 is the download cell
            a_tag = cols[5].find("a")
            if not a_tag or not a_tag.get("href"):
                continue

            # Resolve relative href against the site origin
            rel_url = a_tag["href"]
            full_url = urljoin(self._base_url, rel_url)

            # Pull the timestamp from the filename (ignore query string)
            filename = full_url.rsplit("/", 1)[-1].split("?")[0]
            fdate = self._file_date(filename)

            links.append(full_url)
            if fdate:
                dates.append(fdate)

        # High-water mark for the cache: the latest date seen on this page
        newest = max(dates) if dates else None
        log.info("fetched %d file link(s) from Super-Pharm; newest %s", len(links), newest)
        return links, newest

    def new_links(self, links: list[str], since_date: str | None) -> list[str]:
        """Keep only links newer than the cached high-water mark (or all if none yet)."""
        if since_date is None:
            return list(links)

        # Compare filename dates lexicographically against the last saved date
        fresh = [
            link for link in links
            if (self._file_date(link.rsplit("/", 1)[-1]) or "") > since_date
        ]
        log.info("new_links: %d of %d newer than %s", len(fresh), len(links), since_date)
        return fresh


# Local smoke test — uncomment to run against MinIO
# if __name__ == "__main__":
#     import os
#     from pathlib import Path
#
#     from crawler import Config
#
#     logging.basicConfig(level=logging.INFO)
#
#     # Defaults match local docker-compose MinIO; override via env if needed
#     test_config = Config(
#         source_url="http://prices.super-pharm.co.il/",
#         bucket="raw-prices",
#         s3_endpoint=os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
#         s3_access_key=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
#         s3_secret_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
#         s3_region=os.environ.get("S3_REGION", "us-east-1"),
#         cache_path=Path("./tmp/cache/super_pharm.txt"),
#         download_dir=Path("./tmp/downloads"),
#         link_suffixes=(".gz", ".xml"),
#     )
#
#     crawler = SuperPharmCrawler(test_config)
#     uploaded_keys = crawler.run()  # fetch → filter → download → upload
#     print(uploaded_keys)
