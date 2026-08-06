"""Salim crawler — abstract base + shared single-source pipeline.

A concrete crawler exists per source (e.g. per supermarket chain). Each source
differs in how you log in, how the index page looks, and how dates are encoded,
so subclasses implement just those two source-specific steps:

    - ``fetch()``      authenticate, GET the index, return (links, newest_date)
    - ``new_links()``  given links + the last saved date, return only newer links

Everything shared lives on the base class ``Crawler``::

    links, newest = self.fetch()          # source-specific
    since         = Cacher.load()          # last saved date (high-water mark)
    fresh         = self.new_links(links, since)   # source-specific
    for link in fresh:                     # download then upload, one by one
        Uploader.upload(Downloader.download([link]))
    Cacher.save(newest)                    # advance the mark AFTER success

Only the newest date is cached — not the page.

This module only knows how to run ONE source, given its ``Config``. The
registry of which sources exist, and running all of them together, lives in
``orchestrator.py``.
"""
from __future__ import annotations

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import boto3
import requests

log = logging.getLogger("salim.crawler")

DEFAULT_HEADERS = {
    "User-Agent": "salim-crawler/1.0 (+https://github.com/AlonRR/data-pipeline-2026)",
}


# --------------------------------------------------------------------------- #
# Shared link extraction
# --------------------------------------------------------------------------- #
class _LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.hrefs.append(value)


def extract_links(
    html: str,
    base_url: str | None = None,
    suffixes: tuple[str, ...] | None = None,
) -> list[str]:
    """Return absolute ``<a href>`` links from *html*.

    ``suffixes`` optionally keeps only file-like links, e.g. ``(".gz", ".xml")``.
    """
    extractor = _LinkExtractor()
    extractor.feed(html or "")
    links: list[str] = []
    for href in extractor.hrefs:
        absolute = urljoin(base_url, href) if base_url else href
        if suffixes and not absolute.lower().endswith(suffixes):
            continue
        links.append(absolute)
    return links


# --------------------------------------------------------------------------- #
# Downloader — gets a list of links and downloads the files.
# --------------------------------------------------------------------------- #
class Downloader:
    """Stream-download each link into ``dest_dir`` and return the local paths."""

    def __init__(self, dest_dir: str | os.PathLike, headers: dict | None = None, timeout: int = 60):
        self.dest_dir = Path(dest_dir)
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(headers or DEFAULT_HEADERS)
        self.timeout = timeout

    @staticmethod
    def _filename_for(url: str) -> str:
        name = Path(urlparse(url).path).name
        return name or "download"

    def download(self, links) -> list[Path]:
        paths: list[Path] = []
        for url in links:
            dest = self.dest_dir / self._filename_for(url)
            with self.session.get(url, stream=True, timeout=self.timeout) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        fh.write(chunk)
            log.info("downloaded %s -> %s", url, dest)
            paths.append(dest)
        return paths


# --------------------------------------------------------------------------- #
# Uploader — uploads files to a specified S3 bucket (MinIO / Supabase Storage).
# --------------------------------------------------------------------------- #
class Uploader:
    """Upload local files to an S3-compatible bucket and return their keys."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
        key_prefix: str = "",
    ):
        self.bucket = bucket
        self.key_prefix = key_prefix.strip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist (idempotent)."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)
            log.info("created bucket %s", self.bucket)

    def _key_for(self, path: Path) -> str:
        return f"{self.key_prefix}/{path.name}" if self.key_prefix else path.name

    def upload(self, paths) -> list[str]:
        self.ensure_bucket()
        keys: list[str] = []
        for path in paths:
            path = Path(path)
            key = self._key_for(path)
            self.client.upload_file(str(path), self.bucket, key)
            log.info("uploaded %s -> s3://%s/%s", path, self.bucket, key)
            keys.append(key)
        return keys


# --------------------------------------------------------------------------- #
# Cacher — stores the newest date seen on the last successful run (NOT the page).
# --------------------------------------------------------------------------- #
class Cacher:
    """Persist / retrieve the high-water-mark date, so the next run only picks
    up links newer than it.

    Backed by a local file. For durability across container restarts, point
    ``CACHE_PATH`` at a mounted volume (or swap this for an S3/DB-backed store —
    the slides' "last run save").
    """

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    def load(self) -> str | None:
        if self.path.exists():
            return self.path.read_text(encoding="utf-8").strip() or None
        return None

    def save(self, date: str | None) -> None:
        if not date:
            log.info("no date to checkpoint; leaving %s unchanged", self.path)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(date, encoding="utf-8")
        log.info("checkpoint saved: %s -> %s", date, self.path)


# --------------------------------------------------------------------------- #
# Configuration — one Config per crawler instance.
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    source_url: str
    bucket: str
    s3_endpoint: str | None
    s3_access_key: str | None
    s3_secret_key: str | None
    s3_region: str | None
    cache_path: Path
    download_dir: Path
    link_suffixes: tuple[str, ...] | None
    user_name: str | None = None
    password: str | None = None


# --------------------------------------------------------------------------- #
# Shared infra config — where files land, not what to fetch. The per-source
# half of Config (url/credentials) is filled in by the orchestrator.
# --------------------------------------------------------------------------- #
@dataclass
class InfraConfig:
    bucket: str
    s3_endpoint: str | None
    s3_access_key: str | None
    s3_secret_key: str | None
    s3_region: str | None
    cache_dir: Path
    download_dir: Path


def load_infra_config() -> InfraConfig:
    """Build the shared infra settings from environment variables (see .env.example)."""
    tmp = Path(tempfile.gettempdir()) / "salim-crawler"
    return InfraConfig(
        bucket=os.environ.get("S3_BUCKET", "raw-prices"),
        s3_endpoint=os.environ.get("S3_ENDPOINT_URL"),
        s3_access_key=os.environ.get("S3_ACCESS_KEY"),
        s3_secret_key=os.environ.get("S3_SECRET_KEY"),
        s3_region=os.environ.get("S3_REGION"),
        cache_dir=Path(os.environ.get("CACHE_DIR", tmp / "cache")),
        download_dir=Path(os.environ.get("DOWNLOAD_DIR", tmp / "downloads")),
    )


# --------------------------------------------------------------------------- #
# Crawler — abstract base. Subclass per source; implement fetch + new_links.
# --------------------------------------------------------------------------- #
class Crawler(ABC):
    """Shared crawl pipeline. Subclasses implement the two source-specific steps."""

    name: str  # unique; must match this crawler's key in orchestrator.CRAWLER_CONFIGS

    def __init__(self, config: Config):
        self.config = config
        self._downloader = Downloader(config.download_dir)
        self._uploader = Uploader(
            config.bucket,
            config.s3_endpoint,
            config.s3_access_key,
            config.s3_secret_key,
            config.s3_region,
        )
        self._cacher = Cacher(config.cache_path)

    # --- source-specific (implement these) --- #
    @abstractmethod
    def fetch(self) -> tuple[list[str], str | None]:
        """Authenticate, GET the index page, and return
        ``(all file links, newest date string found on the page)``.
        ``newest`` is ``None`` if the page has no dated entries.
        """

    @abstractmethod
    def new_links(self, links: list[str], since_date: str | None) -> list[str]:
        """Return only the links dated strictly after ``since_date``.
        On the first run ``since_date`` is ``None`` → return all links.
        """

    # --- shared pipeline --- #
    def run(self) -> list[str]:
        """One crawl cycle: fetch → diff by date → download → upload → checkpoint.

        Returns the list of uploaded S3 keys.
        """
        links, newest_date = self.fetch()
        since = self._cacher.load()
        fresh = self.new_links(links, since)

        if not fresh:
            log.info("no new links since %s", since)
            return []

        keys: list[str] = []
        for link in fresh:  # download then upload, one by one
            paths = self._downloader.download([link])
            keys += self._uploader.upload(paths)

        # advance the high-water mark only after a fully successful cycle
        self._cacher.save(newest_date)
        log.info("crawl complete: %d file(s) uploaded; newest date %s", len(keys), newest_date)
        return keys