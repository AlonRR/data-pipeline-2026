"""Runs against a real Postgres (the ``ON CONFLICT ... WHERE`` guard is dialect-specific)."""
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from messages import PriceMessage, PromotionItemMessage, PromotionMessage
from enrichment import Resolution
from repository import Repository
from shared.models import Manufacturer, Price, Product, Promotion, PromotionItem
from tests.support import PostgresTestCase


def price(**overrides) -> PriceMessage:
    base = dict(
        provider="7290", store_id="001", item_code="111", item_name="חלב תנובה 3%", item_type=1,
        manufacturer_raw=None, unit_quantity="ליטר", unit_of_measure="ליטר", quantity=Decimal("1"),
        weighted=False, in_package=Decimal("1"), price=Decimal("6.90"),
        update_time=datetime(2026, 8, 17, 6, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return PriceMessage(**base)


def promotion(**overrides) -> PromotionMessage:
    base = dict(
        provider="7290", store_id="001", promotion_id="p1", description="2 ב-20",
        start_time=datetime(2026, 8, 17, tzinfo=timezone.utc), end_time=datetime(2026, 8, 24, tzinfo=timezone.utc),
        update_time=datetime(2026, 8, 17, 6, 0, tzinfo=timezone.utc),
        items=[PromotionItemMessage("111", 1, Decimal("2"), None, Decimal("20"), None),
               PromotionItemMessage("222", 1, Decimal("2"), None, Decimal("20"), None)],
    )
    base.update(overrides)
    return PromotionMessage(**base)


class RepositoryTest(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.sessions()
        self.repo = Repository(self.session)

    def tearDown(self):
        self.session.close()

    def test_price_message_creates_product_and_price(self):
        self.repo.upsert_prices([price()], manufacturers={("7290", "111"): Resolution("תנובה", "dictionary")})
        self.session.commit()
        product = self.session.get(Product, ("7290", "111"))
        self.assertEqual(product.item_name, "חלב תנובה 3%")
        self.assertEqual(product.manufacturer, "תנובה")
        self.assertEqual(product.manufacturer_status, "resolved")
        row = self.session.get(Price, ("7290", "001", "111"))
        self.assertEqual(row.price, Decimal("6.90"))

    def test_unresolved_manufacturer_is_pending(self):
        self.repo.upsert_prices([price()], manufacturers={})
        self.session.commit()
        self.assertEqual(self.session.get(Product, ("7290", "111")).manufacturer_status, "pending")

    def test_older_price_does_not_overwrite_newer(self):
        newer = price(price=Decimal("7.50"), update_time=datetime(2026, 8, 18, tzinfo=timezone.utc))
        older = price(price=Decimal("6.00"), update_time=datetime(2026, 8, 10, tzinfo=timezone.utc))
        self.repo.upsert_prices([newer], manufacturers={})
        self.session.commit()
        self.repo.upsert_prices([older], manufacturers={})
        self.session.commit()
        self.assertEqual(self.session.get(Price, ("7290", "001", "111")).price, Decimal("7.50"))

    def test_resolved_manufacturer_is_not_reset_by_later_message(self):
        self.repo.upsert_prices([price()], manufacturers={("7290", "111"): Resolution("תנובה", "dictionary")})
        self.session.commit()
        self.repo.upsert_prices([price(price=Decimal("7"))], manufacturers={})
        self.session.commit()
        product = self.session.get(Product, ("7290", "111"))
        self.assertEqual(product.manufacturer, "תנובה")
        self.assertEqual(product.manufacturer_status, "resolved")

    def test_promotion_items_are_replaced_wholesale(self):
        self.repo.upsert_promotions([promotion()])
        self.session.commit()
        shrunk = promotion(update_time=datetime(2026, 8, 18, tzinfo=timezone.utc),
                           items=[PromotionItemMessage("333", 1, None, None, Decimal("5"), None)])
        self.repo.upsert_promotions([shrunk])
        self.session.commit()
        codes = self.session.scalars(select(PromotionItem.item_code)).all()
        self.assertEqual(codes, ["333"])
        self.assertEqual(self.session.get(Promotion, ("7290", "001", "p1")).update_time.day, 18)

    def test_stale_promotion_is_ignored_entirely(self):
        self.repo.upsert_promotions([promotion()])
        self.session.commit()
        stale = promotion(update_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
                          items=[PromotionItemMessage("999", 1, None, None, None, None)])
        self.repo.upsert_promotions([stale])
        self.session.commit()
        codes = sorted(self.session.scalars(select(PromotionItem.item_code)).all())
        self.assertEqual(codes, ["111", "222"])

    def test_newest_publication_wins_within_one_batch(self):
        newer = price(price=Decimal("7.50"), update_time=datetime(2026, 8, 18, tzinfo=timezone.utc))
        older = price(price=Decimal("6.00"), update_time=datetime(2026, 8, 10, tzinfo=timezone.utc))
        self.repo.upsert_prices([newer, older], manufacturers={})
        self.session.commit()
        self.assertEqual(self.session.get(Price, ("7290", "001", "111")).price, Decimal("7.50"))
        newer_promo = promotion(update_time=datetime(2026, 8, 18, tzinfo=timezone.utc),
                                items=[PromotionItemMessage("333", 1, None, None, None, None)])
        self.repo.upsert_promotions([newer_promo, promotion()])
        self.session.commit()
        self.assertEqual(self.session.scalars(select(PromotionItem.item_code)).all(), ["333"])

    def test_same_batch_duplicate_keys_do_not_fail(self):
        self.repo.upsert_prices([price(), price(price=Decimal("1"))], manufacturers={})
        self.session.commit()
        self.assertIsNotNone(self.session.get(Price, ("7290", "001", "111")))

    def test_seed_brands_and_cache_roundtrip(self):
        self.repo.seed_brands({"תנובה": "תנובה"})
        self.repo.remember("קולה זירו", "Coca-Cola", source="llm", model="m")
        self.session.commit()
        self.assertEqual(self.repo.load_cache(), {"קולה זירו": "Coca-Cola"})
        self.assertEqual(self.repo.load_brands(), {"תנובה": "תנובה"})
        # seeding again never overwrites
        self.repo.seed_brands({"תנובה": "OTHER"})
        self.session.commit()
        self.assertEqual(self.session.get(Manufacturer, "תנובה").manufacturer, "תנובה")


if __name__ == "__main__":
    unittest.main()
