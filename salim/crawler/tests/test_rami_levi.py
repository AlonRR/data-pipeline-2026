from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummyS3Client:
    def head_bucket(self, **kwargs) -> None:
        return None

    def create_bucket(self, **kwargs) -> None:
        return None

    def upload_file(self, *args, **kwargs) -> None:
        return None


sys.modules.setdefault("boto3", types.SimpleNamespace(client=lambda *args, **kwargs: _DummyS3Client()))

from crawler import Config
from concrete_crawlers.rami_levi import RamiLeviCrawler


class _FakeResponse:
    def __init__(self, *, text: str = "", json_data: dict | None = None, status_code: int = 200):
        self.text = text
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self._json_data or {}


class _FakeSession:
    def __init__(self, *, get_responses: list[_FakeResponse], post_responses: list[_FakeResponse]):
        self.headers: dict[str, str] = {}
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []
        self._get_responses = list(get_responses)
        self._post_responses = list(post_responses)

    def get(self, url: str, **kwargs):
        self.get_calls.append({"url": url, **kwargs})
        return self._get_responses.pop(0)

    def post(self, url: str, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return self._post_responses.pop(0)


class RamiLeviCrawlerTests(unittest.TestCase):
    def _config(self) -> Config:
        tmpdir = Path(tempfile.mkdtemp())
        return Config(
            source_url="https://url.publishedprices.co.il/login",
            bucket="raw-prices",
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            cache_path=tmpdir / "rami_levi.txt",
            download_dir=tmpdir / "downloads",
            link_suffixes=None,
            user_name="RamiLevi",
            password="",
        )

    def test_fetch_logs_in_filters_files_sets_newest_and_reuses_authenticated_session(self):
        session = _FakeSession(
            get_responses=[
                _FakeResponse(text='<meta name="csrftoken" content="login-token">'),
                _FakeResponse(text='<meta name="csrftoken" content="listing-token">'),
            ],
            post_responses=[
                _FakeResponse(text="<html>ok</html>"),
                _FakeResponse(
                    json_data={
                        "aaData": [
                            {"type": "file", "fname": "PriceFull7290058140886-001-20260805-010203.gz"},
                            {"type": "file", "fname": "PromoFull7290058140886-001-20260806-121314.gz"},
                            {"type": "file", "fname": "StoresFull7290058140886-001-20260806-121314.gz"},
                            {"type": "dir", "fname": "archive"},
                        ],
                        "iTotalRecords": 4,
                    }
                ),
            ],
        )
        crawler = RamiLeviCrawler(self._config())

        with patch("concrete_crawlers.cerberus.requests.Session", return_value=session):
            links, newest = crawler.fetch()

        self.assertEqual(
            session.post_calls[0]["data"]["username"],
            "RamiLevi",
        )
        self.assertEqual(
            links,
            [
                "https://url.publishedprices.co.il/file/d/PriceFull7290058140886-001-20260805-010203.gz",
                "https://url.publishedprices.co.il/file/d/PromoFull7290058140886-001-20260806-121314.gz",
            ],
        )
        self.assertEqual(newest, "20260806121314")
        self.assertIs(crawler._downloader.session, session)

    def test_new_links_returns_only_files_newer_than_checkpoint(self):
        crawler = RamiLeviCrawler(self._config())
        links = [
            "https://url.publishedprices.co.il/file/d/PriceFull7290058140886-001-20260805-010203.gz",
            "https://url.publishedprices.co.il/file/d/PromoFull7290058140886-001-20260806-121314.gz",
            "https://url.publishedprices.co.il/file/d/PriceFull7290058140886-001-20260804-235959.gz",
        ]

        fresh = crawler.new_links(links, "20260805010203")

        self.assertEqual(
            fresh,
            ["https://url.publishedprices.co.il/file/d/PromoFull7290058140886-001-20260806-121314.gz"],
        )


if __name__ == "__main__":
    unittest.main()
