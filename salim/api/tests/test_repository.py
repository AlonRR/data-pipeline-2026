"""Runs against a real Postgres (mirrors services/loader/tests/test_repository.py)."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from api import repository as repo
from shared.models import CatalogProduct, Chain, Price, Product, Promotion, PromotionItem
from api.tests.support import PostgresTestCase

NOW = datetime.now(timezone.utc)  # promotion windows are relative to real "now"


def catalog_product(**overrides) -> CatalogProduct:
    base = dict(product_id="gtin:111", gtin="111", slug="milk-3", display_name="חלב תנובה 3%", manufacturer="תנובה")
    base.update(overrides)
    return CatalogProduct(**base)


def product(**overrides) -> Product:
    base = dict(provider="7290", item_code="111", catalog_product_id="gtin:111", item_name="חלב תנובה 3%", item_type=1)
    base.update(overrides)
    return Product(**base)


def price(**overrides) -> Price:
    base = dict(provider="7290", store_id="001", item_code="111", price=Decimal("6.90"), update_time=NOW)
    base.update(overrides)
    return Price(**base)


class RepositoryTest(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.session = self.sessions()
        self.session.add(Chain(chain_id="7290", name="שופרסל"))
        self.session.add(Chain(chain_id="7291", name="ויקטורי"))
        self.session.commit()

    def tearDown(self):
        self.session.close()

    # ------------------------------------------------------------- list_products
    def test_list_products_filters_by_q(self):
        self.session.add_all([
            catalog_product(product_id="gtin:111", display_name="חלב תנובה 3%", slug="milk-3"),
            catalog_product(product_id="gtin:222", display_name="קוטג' תנובה", slug="cottage", gtin="222"),
        ])
        self.session.commit()

        results = repo.list_products(self.session, q="חלב")
        self.assertEqual([p.product_id for p in results], ["gtin:111"])

    def test_list_products_filters_by_manufacturer_case_insensitive(self):
        self.session.add_all([
            catalog_product(product_id="gtin:111", manufacturer="תנובה"),
            catalog_product(product_id="gtin:222", manufacturer="שטראוס", gtin="222", slug="s2"),
        ])
        self.session.commit()

        results = repo.list_products(self.session, manufacturer="תנובה")
        self.assertEqual([p.product_id for p in results], ["gtin:111"])

    def test_list_products_filters_by_has_promotion(self):
        self.session.add_all([catalog_product(product_id="gtin:111"), catalog_product(product_id="gtin:222", gtin="222", slug="s2")])
        self.session.add_all([product(), product(provider="7290", item_code="222", catalog_product_id="gtin:222")])
        self.session.flush()  # products must exist before promotion_items reference them
        self.session.add(Promotion(provider="7290", store_id="001", promotion_id="p1", start_time=NOW - timedelta(days=1), end_time=NOW + timedelta(days=1)))
        self.session.flush()  # promotion must exist before its items reference it
        self.session.add(PromotionItem(provider="7290", store_id="001", promotion_id="p1", item_code="111", discount_price=Decimal("5")))
        self.session.commit()

        promoted = repo.list_products(self.session, has_promotion=True)
        not_promoted = repo.list_products(self.session, has_promotion=False)
        self.assertEqual([p.product_id for p in promoted], ["gtin:111"])
        self.assertEqual([p.product_id for p in not_promoted], ["gtin:222"])

    def test_list_products_pagination(self):
        self.session.add_all([
            catalog_product(product_id=f"gtin:{i}", display_name=f"p{i}", slug=f"s{i}", gtin=str(i)) for i in range(5)
        ])
        self.session.commit()

        page = repo.list_products(self.session, limit=2, offset=1)
        self.assertEqual(len(page), 2)

    # --------------------------------------------------------------- get_product
    def test_get_product_found_and_missing(self):
        self.session.add(catalog_product())
        self.session.commit()

        self.assertIsNotNone(repo.get_product(self.session, "gtin:111"))
        self.assertIsNone(repo.get_product(self.session, "gtin:does-not-exist"))

    # ------------------------------------------------------------ product_prices
    def test_product_prices_lowest_orders_and_limits(self):
        self.session.add_all([catalog_product(), catalog_product(product_id="gtin:other", gtin="other", slug="other")])
        self.session.add_all([
            product(provider="7290", item_code="111"),
            product(provider="7291", item_code="222", catalog_product_id="gtin:other"),  # different product: must be excluded
        ])
        self.session.flush()  # products must exist before prices reference them
        self.session.add_all([
            price(provider="7290", store_id="001", item_code="111", price=Decimal("6.90")),
            price(provider="7290", store_id="002", item_code="111", price=Decimal("5.50")),
            price(provider="7291", store_id="001", item_code="222", price=Decimal("9.90")),
        ])
        self.session.commit()

        cheapest = repo.product_prices(self.session, "gtin:111", order="asc", limit=1)
        self.assertEqual(len(cheapest), 1)
        self.assertEqual(cheapest[0]["price"], Decimal("5.50"))
        self.assertEqual(cheapest[0]["chain_name"], "שופרסל")

    def test_product_prices_highest(self):
        self.session.add_all([catalog_product(), catalog_product(product_id="gtin:other", gtin="other", slug="other")])
        self.session.add_all([
            product(provider="7290", item_code="111"),
            product(provider="7291", item_code="222", catalog_product_id="gtin:other"),  # different product: must be excluded
        ])
        self.session.flush()
        self.session.add_all([
            price(provider="7290", store_id="001", item_code="111", price=Decimal("6.90")),
            price(provider="7291", store_id="001", item_code="222", price=Decimal("9.90")),
        ])
        self.session.commit()

        priciest = repo.product_prices(self.session, "gtin:111", order="desc", limit=10)
        self.assertEqual([row["price"] for row in priciest], [Decimal("6.90")])

    def test_product_prices_empty_for_unknown_product(self):
        self.assertEqual(repo.product_prices(self.session, "gtin:missing"), [])

    # --------------------------------------------------------- product_promotions
    def test_product_promotions_active_only_excludes_expired(self):
        self.session.add(catalog_product())
        self.session.add(product())
        self.session.flush()
        self.session.add_all([
            Promotion(provider="7290", store_id="001", promotion_id="active", description="2 ב-20",
                      start_time=NOW - timedelta(days=1), end_time=NOW + timedelta(days=1)),
            Promotion(provider="7290", store_id="001", promotion_id="expired", description="ישן",
                      start_time=NOW - timedelta(days=10), end_time=NOW - timedelta(days=1)),
        ])
        self.session.flush()
        self.session.add_all([
            PromotionItem(provider="7290", store_id="001", promotion_id="active", item_code="111", discount_price=Decimal("20")),
            PromotionItem(provider="7290", store_id="001", promotion_id="expired", item_code="111", discount_price=Decimal("15")),
        ])
        self.session.commit()

        active = repo.product_promotions(self.session, "gtin:111", active_only=True)
        everything = repo.product_promotions(self.session, "gtin:111", active_only=False)
        self.assertEqual([p["promotion_id"] for p in active], ["active"])
        self.assertEqual({p["promotion_id"] for p in everything}, {"active", "expired"})

    def test_product_promotions_groups_items_under_one_promotion(self):
        self.session.add(catalog_product())
        self.session.add_all([product(), product(provider="7290", item_code="222", catalog_product_id="gtin:111")])
        self.session.flush()
        self.session.add(Promotion(provider="7290", store_id="001", promotion_id="p1", start_time=NOW - timedelta(days=1), end_time=NOW + timedelta(days=1)))
        self.session.flush()
        self.session.add_all([
            PromotionItem(provider="7290", store_id="001", promotion_id="p1", item_code="111", discount_price=Decimal("10")),
            PromotionItem(provider="7290", store_id="001", promotion_id="p1", item_code="222", discount_price=Decimal("10")),
        ])
        self.session.commit()

        promotions = repo.product_promotions(self.session, "gtin:111")
        self.assertEqual(len(promotions), 1)  # one promotion row, not one per item
        self.assertEqual({item["item_code"] for item in promotions[0]["items"]}, {"111", "222"})

    def test_product_promotions_empty_means_no_promotion(self):
        self.session.add(catalog_product())
        self.session.add(product())
        self.session.commit()

        self.assertEqual(repo.product_promotions(self.session, "gtin:111"), [])


if __name__ == "__main__":
    unittest.main()
