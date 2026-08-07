from __future__ import annotations

import os
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

from concrete_crawlers.cerberus import CerberusCrawler
from crawler import InfraConfig
import orchestrator


class _RecordingCrawler(CerberusCrawler):
    instances: list["_RecordingCrawler"] = []

    def __init__(self, config):
        super().__init__(config)
        self.__class__.instances.append(self)

    def run(self) -> list[str]:
        return [f"{self.name}-result"]


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingCrawler.instances.clear()

    def _infra(self) -> InfraConfig:
        tmpdir = Path(tempfile.mkdtemp())
        return InfraConfig(
            bucket="raw-prices",
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            cache_dir=tmpdir / "cache",
            download_dir=tmpdir / "downloads",
        )

    def test_build_config_uses_registration_name_for_paths_and_password_env_var(self):
        infra = self._infra()
        settings = {
            "source_url": "https://url.publishedprices.co.il/login",
            "user_name": "RamiLevi",
            "password": "fallback",
        }

        with patch.dict(os.environ, {"CRAWLER_RAMI_LEVI_PASSWORD": "from-env"}, clear=False):
            config = orchestrator._build_config("rami_levi", settings, infra)

        self.assertEqual(config.name, "rami_levi")
        self.assertEqual(config.password, "from-env")
        self.assertEqual(config.cache_path, infra.cache_dir / "rami_levi.txt")
        self.assertEqual(config.download_dir, infra.download_dir / "rami_levi")

    def test_run_registers_both_cerberus_configurations_with_distinct_instance_names(self):
        registrations = [
            orchestrator.CrawlerRegistration(name="yohananof", crawler_cls=_RecordingCrawler),
            orchestrator.CrawlerRegistration(name="rami_levi", crawler_cls=_RecordingCrawler),
        ]

        with patch("orchestrator.load_infra_config", return_value=self._infra()):
            results = orchestrator.run(registrations)

        self.assertEqual(
            results,
            {
                "yohananof": ["yohananof-result"],
                "rami_levi": ["rami_levi-result"],
            },
        )
        self.assertEqual([crawler.name for crawler in _RecordingCrawler.instances], ["yohananof", "rami_levi"])
        self.assertTrue(str(_RecordingCrawler.instances[0].config.download_dir).endswith("yohananof"))
        self.assertTrue(str(_RecordingCrawler.instances[1].config.download_dir).endswith("rami_levi"))


if __name__ == "__main__":
    unittest.main()
