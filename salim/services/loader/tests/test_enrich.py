import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import text

from enrich import LlmResolver, run_backfill
from repository import Repository
from shared.models import Manufacturer, Product
from tests.support import PostgresTestCase
from tests.test_repository import price


def _response(payload) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))],
    )


class LlmResolverTest(unittest.TestCase):
    def test_maps_ids_back_and_treats_blank_as_none(self):
        client = MagicMock()
        client.messages.create.return_value = _response(
            {"results": [{"id": 1, "manufacturer": "תנובה"}, {"id": 2, "manufacturer": None}, {"id": 3, "manufacturer": "  "}]}
        )
        resolver = LlmResolver(client, model="claude-haiku-4-5")
        out = resolver.resolve([(1, "חלב תנובה"), (2, "מלפפון"), (3, "לחם")])
        self.assertEqual(out, {1: "תנובה", 2: None, 3: None})
        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-haiku-4-5")
        sent = json.loads(kwargs["messages"][0]["content"])
        self.assertEqual([i["id"] for i in sent], [1, 2, 3])
        self.assertIn("json_schema", json.dumps(kwargs["output_config"]))

    def test_ids_not_answered_are_left_out(self):
        client = MagicMock()
        client.messages.create.return_value = _response({"results": [{"id": 1, "manufacturer": "x"}]})
        out = LlmResolver(client, model="m").resolve([(1, "a"), (2, "b")])
        self.assertEqual(out, {1: "x"})

    def test_refusal_raises(self):
        client = MagicMock()
        client.messages.create.return_value = SimpleNamespace(stop_reason="refusal", content=[])
        with self.assertRaises(RuntimeError):
            LlmResolver(client, model="m").resolve([(1, "a")])


class FakeResolver:
    model = "fake"

    def __init__(self, answers=None, fail=False):
        self.answers = answers or {}
        self.fail = fail
        self.calls = []

    def resolve(self, batch):
        self.calls.append(list(batch))
        if self.fail:
            raise RuntimeError("api down")
        return {i: self.answers.get(name) for i, name in batch}


class BackfillTest(PostgresTestCase):
    def setUp(self):
        super().setUp()
        with self.sessions() as s:
            Repository(s).upsert_prices(
                [price(item_code="1", item_name="חלב תנובה"), price(item_code="2", item_name="מלפפון"),
                 price(item_code="3", item_name="קולה", store_id="002")],
                manufacturers={},
            )
            s.commit()

    def test_nothing_pending_means_no_llm_call(self):
        with self.sessions() as s:
            s.execute(text("UPDATE products SET manufacturer_status='resolved'"))
            s.commit()
        resolver = FakeResolver()
        stats = run_backfill(self.sessions, resolver, batch_size=50, max_attempts=3)
        self.assertEqual(resolver.calls, [])
        self.assertEqual(stats.resolved + stats.unknown + stats.failed, 0)

    def test_pending_products_get_resolved_or_unknown_and_cached(self):
        resolver = FakeResolver({"חלב תנובה": "תנובה", "קולה": "Coca-Cola"})
        stats = run_backfill(self.sessions, resolver, batch_size=2, max_attempts=3)
        self.assertEqual((stats.resolved, stats.unknown, stats.failed), (2, 1, 0))
        self.assertEqual(len(resolver.calls), 2)  # 3 names, batches of 2
        with self.sessions() as s:
            self.assertEqual(s.get(Product, ("7290", "1")).manufacturer, "תנובה")
            self.assertEqual(s.get(Product, ("7290", "1")).manufacturer_status, "resolved")
            self.assertEqual(s.get(Product, ("7290", "2")).manufacturer_status, "unknown")
            self.assertIsNone(s.get(Product, ("7290", "2")).manufacturer)
            self.assertEqual(s.get(Manufacturer, "קולה").manufacturer, "Coca-Cola")
            self.assertEqual(s.get(Manufacturer, "קולה").source, "llm")
            self.assertIsNone(s.get(Manufacturer, "מלפפון").manufacturer)

    def test_failure_bumps_attempts_and_stops_after_max(self):
        resolver = FakeResolver(fail=True)
        for _ in range(3):
            run_backfill(self.sessions, resolver, batch_size=50, max_attempts=3)
        self.assertEqual(len(resolver.calls), 3)
        run_backfill(self.sessions, resolver, batch_size=50, max_attempts=3)
        self.assertEqual(len(resolver.calls), 3, "exhausted rows must not be retried")
        with self.sessions() as s:
            self.assertEqual(s.get(Product, ("7290", "1")).manufacturer_attempts, 3)
            self.assertEqual(s.get(Product, ("7290", "1")).manufacturer_status, "pending")

    def test_same_name_across_products_is_asked_once(self):
        with self.sessions() as s:
            Repository(s).upsert_prices([price(provider="9999", item_code="77", item_name="חלב תנובה")], manufacturers={})
            s.commit()
        resolver = FakeResolver({"חלב תנובה": "תנובה"})
        run_backfill(self.sessions, resolver, batch_size=50, max_attempts=3)
        asked = [name for call in resolver.calls for _, name in call]
        self.assertEqual(asked.count("חלב תנובה"), 1)
        with self.sessions() as s:
            self.assertEqual(s.get(Product, ("9999", "77")).manufacturer, "תנובה")


if __name__ == "__main__":
    unittest.main()
