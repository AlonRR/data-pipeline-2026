"""Batch processing end to end against Postgres."""
import json
import unittest

from sqlalchemy import select

from consumer import BatchProcessor
from enrichment import BrandDictionary
from shared.models import Price, Product, PromotionItem
from tests.support import PostgresTestCase
from tests.test_messages import PRICE, PROMOTION


class BatchProcessorTest(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.processor = BatchProcessor(self.sessions, BrandDictionary({"תנובה": "תנובה"}), cache={})

    def test_mixed_batch_lands_and_reports_poison(self):
        bodies = [
            (1, json.dumps(PRICE).encode()),
            (2, json.dumps(PROMOTION).encode()),
            (3, b"not json at all"),
            (4, json.dumps({"itemCode": "x", "price": 1}).encode()),  # no store/provider
        ]
        result = self.processor.process(bodies)
        self.assertEqual(result.loaded, [1, 2])
        self.assertEqual([tag for tag, _ in result.poison], [3, 4])
        with self.sessions() as s:
            self.assertEqual(s.get(Product, ("7290027600007", "7290000066318")).manufacturer, "תנובה")
            self.assertIsNotNone(s.get(Price, ("7290027600007", "005", "7290000066318")))
            self.assertEqual(s.scalars(select(PromotionItem.item_code)).all(), ["729"])

    def test_row_the_database_rejects_is_poison_not_a_blocker(self):
        too_long = dict(PRICE, itemCode="999", itemName="x" * 600)
        bodies = [(1, json.dumps(PRICE).encode()), (2, json.dumps(too_long).encode())]
        result = self.processor.process(bodies)
        self.assertEqual(result.loaded, [1])
        self.assertEqual([tag for tag, _ in result.poison], [2])
        with self.sessions() as s:
            self.assertIsNotNone(s.get(Product, ("7290027600007", "7290000066318")))
            self.assertIsNone(s.get(Product, ("7290027600007", "999")))

    def test_empty_batch_is_a_noop(self):
        result = self.processor.process([])
        self.assertEqual(result.loaded, [])
        self.assertEqual(result.poison, [])


if __name__ == "__main__":
    unittest.main()
